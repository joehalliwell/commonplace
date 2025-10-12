import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pytest

from commonplace._import._commands import import_
from commonplace._import._serializer import MarkdownSerializer
from commonplace._import._types import EventLog, Message, Role

SAMPLE_EXPORTS_DIR = Path(__file__).parent / "resources" / "sample-exports"
SAMPLE_EXPORT_NAMES = [p.name for p in SAMPLE_EXPORTS_DIR.glob("*")]


@dataclass
class SampleExport:
    name: str  # A short identifier for this sample
    path: Path  # Path to the zip file for this sample


@pytest.fixture(scope="module", params=SAMPLE_EXPORT_NAMES)
def sample_export(request, tmp_path_factory):
    """Make a sample export archive from the resources directory"""
    name: str = request.param
    source_path: Path = SAMPLE_EXPORTS_DIR / name
    if source_path.is_dir() and source_path.suffix == ".zip":
        # Create a zip file from the directory
        tmp_path = tmp_path_factory.mktemp(name)
        zipfile = shutil.make_archive(tmp_path / name, "zip", SAMPLE_EXPORTS_DIR / name)
        return SampleExport(name, Path(zipfile))

    return SampleExport(name, source_path)


def test_import(sample_export, test_repo, snapshot):
    """End-to-end snapshot-based test for all samples"""
    import_(sample_export.path, test_repo, user="Human")

    buffer = ""
    for path in sorted((test_repo.root / "chats").glob("**/*.md")):
        buffer += f"<!-- Contents of {path.relative_to(test_repo.root).as_posix()} -->\n"
        buffer += open(path, "r").read() + "\n"

    snapshot.assert_match(buffer, snapshot_name="combined.md")


def test_serialize_log(snapshot):
    """Test basic serialization of ActivityLog to markdown."""
    serializer = MarkdownSerializer(human="Human", assistant="Assistant")

    messages = [
        Message(
            sender=Role.USER,
            content="Hello",
            created=datetime(2024, 1, 1, 12, 0, 0),
            metadata={"id": "message-0"},
        ),
        Message(
            sender=Role.ASSISTANT,
            content="Hi there!",
            created=datetime(2024, 1, 1, 12, 0, 1),
            metadata={"id": "message-1"},
        ),
    ]

    log = EventLog(
        source="test",
        title="Test Chat",
        created=datetime(2024, 1, 1, 12, 0, 0),
        events=messages,
        metadata={"id": "log-0"},
    )

    result = serializer.serialize(log)
    snapshot.assert_match(result, "log.md")


def test_import_preserves_user_metadata(test_repo, tmp_path_factory):
    """Test that re-importing preserves user-added metadata."""
    from commonplace._import._commands import import_

    # Use existing sample export
    sample_dir = SAMPLE_EXPORTS_DIR / "claude.zip"
    export_path = tmp_path_factory.mktemp("export") / "claude.zip"
    shutil.make_archive(str(export_path.with_suffix("")), "zip", sample_dir)

    # First import
    import_(export_path, test_repo, user="Human")

    # Find the first imported file
    imported_files = sorted((test_repo.root / "chats").glob("**/*.md"))
    assert len(imported_files) > 0
    imported_file = imported_files[0]

    # Add user metadata to the frontmatter
    original_content = imported_file.read_text()
    # Find the end of frontmatter and insert user fields before it
    updated_content = original_content.replace(
        "\n---\n",
        "\ntags:\n- important\n- test\nrating: 5\n---\n",
        1,  # Only replace first occurrence
    )
    imported_file.write_text(updated_content)

    # Re-import the same export
    import_(export_path, test_repo, user="Human")

    # Verify user metadata was preserved
    from commonplace._utils import parse_frontmatter

    final_content = imported_file.read_text()
    final_metadata, _ = parse_frontmatter(final_content)

    assert "tags" in final_metadata
    assert "important" in final_metadata["tags"]
    assert "test" in final_metadata["tags"]
    assert final_metadata["rating"] == 5
