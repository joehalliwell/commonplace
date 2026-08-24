import gzip
import json
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pytest

from commonplace._import._claude_export import ClaudeExportImporter
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
        buffer += path.read_text(encoding="utf-8") + "\n"

    snapshot.assert_match(buffer, snapshot_name="combined.md")


def test_serialize_log(snapshot):
    """Test basic serialization of ActivityLog to markdown."""
    serializer = MarkdownSerializer(human="Human", assistant="Assistant")

    messages = [
        Message(
            sender=Role.USER,
            content="Hello",
            created=datetime(2024, 1, 1, 12, 0, 0),  # noqa: DTZ001 - naive on purpose; snapshots pin the rendering
            metadata={"id": "message-0"},
        ),
        Message(
            sender=Role.ASSISTANT,
            content="Hi there!",
            created=datetime(2024, 1, 1, 12, 0, 1),  # noqa: DTZ001 - naive on purpose; snapshots pin the rendering
            metadata={"id": "message-1"},
        ),
    ]

    log = EventLog(
        source="test",
        title="Test Chat",
        created=datetime(2024, 1, 1, 12, 0, 0),  # noqa: DTZ001 - naive on purpose; snapshots pin the rendering
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


def _wire_archive(path: Path, fetched_at: str, marker: str) -> Path:
    """A one-conversation Claude wire archive, captured at `fetched_at`, saying `marker`."""
    thread = {
        "uuid": "ordering-cid",
        "name": "Ordering",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "chat_messages": [
            {
                "uuid": "m1",
                "sender": "human",
                "text": marker,
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
            }
        ],
    }
    lines = [
        {"wire": "claude", "version": 3, "fetched_at": fetched_at, "fetched_by": "test/0"},
        # From v2 the response is the verbatim body text, not a parsed object.
        {"endpoint": "conversations", "response": json.dumps([thread])},
        {"endpoint": "conversation", "cid": thread["uuid"], "response": json.dumps(thread)},
    ]
    with gzip.open(path, "wt", encoding="utf-8") as f:
        for line in lines:
            f.write(json.dumps(line) + "\n")
    return path


def test_import_directory_applies_the_newest_capture_last(test_repo, tmp_path):
    """Directory order is arbitrary, so without this an older snapshot silently clobbers a newer one."""
    archives = tmp_path / "archives"
    archives.mkdir()
    # Sorted by name, the newer capture comes first and loses.
    _wire_archive(archives / "a.jsonl.gz", "2026-08-15T00:00:00+00:00", "NEWER")
    _wire_archive(archives / "b.jsonl.gz", "2026-08-13T00:00:00+00:00", "OLDER")

    import_(archives, test_repo, user="Human")

    imported = next((test_repo.root / "chats").glob("**/*.md")).read_text()
    assert "NEWER" in imported
    assert "OLDER" not in imported


CLAUDE_CONVERSATIONS = SAMPLE_EXPORTS_DIR / "claude.zip" / "conversations.json"


def test_can_import_a_stored_conversations_blob():
    """A blob the repo stored must be readable back — provenance that can't be re-read isn't provenance."""
    assert ClaudeExportImporter().can_import(CLAUDE_CONVERSATIONS)


def test_import_a_stored_conversations_blob_yields_logs():
    """The conversations file holds all the importer reads; the zip around it was only packaging."""
    assert ClaudeExportImporter().import_(CLAUDE_CONVERSATIONS)


def test_claude_importer_declines_a_chatgpt_conversations_file(tmp_path):
    """conversations.json is not a Claude-specific name, so content has to decide."""
    path = tmp_path / "conversations.json"
    path.write_text(json.dumps([{"title": "x", "mapping": {}}]))

    assert not ClaudeExportImporter().can_import(path)


def test_import_a_directory_of_wire_archives_creates_notes(test_repo, tmp_path):
    """Importing a directory is a documented flow, and nested progress bars used to crash it."""
    shutil.copy(SAMPLE_EXPORTS_DIR / "claude.jsonl.gz", tmp_path / "claude.jsonl.gz")

    import_(tmp_path, test_repo, user="Human")

    assert list((test_repo.root / "chats").glob("**/*.md"))


def test_import_a_directory_of_stored_blobs_creates_notes(test_repo, tmp_path):
    """The re-import path: point at the blob store and get the chats back."""
    blobs = tmp_path / "blobs" / "d34db33f"
    blobs.mkdir(parents=True)
    shutil.copy(CLAUDE_CONVERSATIONS, blobs / "conversations.json")

    import_(tmp_path / "blobs", test_repo, user="Human")

    assert list((test_repo.root / "chats").glob("**/*.md"))


ARTIFACT_CODE = """Here is the code:

<antArtifact identifier="demo" type="application/vnd.ant.code" language="python" title="Demo">
class ConstraintSystem:
    def __init__(self):
        self.constraints: List[Callable[[Dict[str, any]], bool]] = []

    def add_variable(self, name: str, domain: set):
        self.variables[name] = domain
</antArtifact>

That's it.
"""


def _serialize_message(content: str) -> str:
    serializer = MarkdownSerializer(human="Human", assistant="Assistant")
    log = EventLog(
        source="test",
        title="Artifacts",
        created=datetime(2024, 1, 1, 12, 0, 0),  # noqa: DTZ001 - naive on purpose
        events=[
            Message(
                sender=Role.ASSISTANT,
                content=content,
                created=datetime(2024, 1, 1, 12, 0, 0),  # noqa: DTZ001 - naive on purpose
                metadata={},
            )
        ],
        metadata={},
    )
    return serializer.serialize(log)


def test_serialize_keeps_artifact_code_line_structure():
    """Code in an artifact must survive: reflowing it changes what the model said."""
    out = _serialize_message(ARTIFACT_CODE)
    assert "    def add_variable(self, name: str, domain: set):" in out
    assert "class ConstraintSystem:" in out


def test_serialize_keeps_unindented_artifact_code_on_its_own_lines():
    """The corpus case: past the blank line an HTML block ends, and column-0 code became prose."""
    content = (
        '<antArtifact identifier="demo" type="application/vnd.ant.code" language="python" title="Demo">\n'
        "import sys\n"
        "\n"
        "def main(argv: list[str]) -> int:\n"
        "    return 0\n"
        "</antArtifact>\n"
    )
    out = _serialize_message(content)
    assert "\ndef main(argv: list[str]) -> int:\n" in out
    assert "    return 0" in out


def test_serialize_does_not_escape_brackets_in_artifact_code():
    """Escaped brackets are not what was written, and not valid Python."""
    out = _serialize_message(ARTIFACT_CODE)
    assert "List[Callable[[Dict[str, any]], bool]]" in out
    assert "\\[" not in out


def test_serialize_leaves_markdown_artifacts_as_prose():
    """A markdown artifact is markdown: fencing it would turn a document into a code block."""
    content = (
        '<antArtifact identifier="essay" type="text/markdown" title="Essay">\n'
        "# Heading\n\nSome *prose* that should stay prose.\n"
        "</antArtifact>\n"
    )
    out = _serialize_message(content)
    assert "# Heading" in out
    assert "```" not in out
