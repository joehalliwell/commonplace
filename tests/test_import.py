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


def _prepare_export(source_path: Path, tmp_dir: Path) -> Path:
    """Prepare a sample export for testing — zip directories, copy files as-is."""
    if source_path.is_dir() and source_path.suffix == ".zip":
        return Path(shutil.make_archive(tmp_dir / source_path.stem, "zip", source_path))
    return source_path


@dataclass
class SampleExport:
    name: str  # A short identifier for this sample
    path: Path  # Path to the zip file for this sample


@pytest.fixture(scope="module", params=SAMPLE_EXPORT_NAMES)
def sample_export(request, tmp_path_factory):
    """Make a sample export archive from the resources directory"""
    name: str = request.param
    tmp_path = tmp_path_factory.mktemp(name)
    path = _prepare_export(SAMPLE_EXPORTS_DIR / name, tmp_path)
    return SampleExport(name, path)


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

    export_path = _prepare_export(SAMPLE_EXPORTS_DIR / "claude.zip", tmp_path_factory.mktemp("export"))

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


@pytest.fixture
def claude_export(tmp_path_factory):
    """Create a zip archive from the claude.zip sample export directory."""
    return _prepare_export(SAMPLE_EXPORTS_DIR / "claude.zip", tmp_path_factory.mktemp("export"))


@pytest.fixture
def index_spy(monkeypatch):
    """Mock the index function and return a list that records calls."""
    calls = []

    def mock_index(repo, rebuild):
        calls.append((repo, rebuild))

    import commonplace._search._commands

    monkeypatch.setattr(commonplace._search._commands, "index", mock_index)
    return calls


def test_import_no_index_skips_indexing(test_repo, index_spy, claude_export):
    """Test that import with auto_index=False does not trigger indexing."""
    import_(claude_export, test_repo, user="Human", auto_index=False)
    assert len(index_spy) == 0


def test_import_with_index_triggers_indexing(test_repo, index_spy, claude_export):
    """Test that import with auto_index=True does trigger indexing."""
    import_(claude_export, test_repo, user="Human", auto_index=True)
    assert len(index_spy) == 1


def test_import_cli_no_index_flag(test_app, index_spy, claude_export):
    """Test that 'import --no-index' CLI flag prevents indexing."""
    result = test_app(["import", "--no-index", str(claude_export)])
    assert result == 0
    assert len(index_spy) == 0
