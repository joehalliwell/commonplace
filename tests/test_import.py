import json
import re
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from zipfile import BadZipFile, ZipFile

import pytest

from commonplace._import._chatgpt import ChatGptImporter
from commonplace._import._claude_code import ClaudeCodeImporter
from commonplace._import._claude_export import ClaudeExportImporter
from commonplace._import._commands import import_
from commonplace._import._gemini_takeout import GeminiTakeoutImporter
from commonplace._import._serializer import MarkdownSerializer
from commonplace._import._types import EventLog, Message, Role
from commonplace._import._zip import zip_contains
from commonplace._utils import dump_frontmatter, load_frontmatter

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


@pytest.fixture
def pinned_version(monkeypatch):
    """Hold `generated.by` still, so snapshots don't move with every release."""
    monkeypatch.setattr("commonplace._import._commands.__version__", "1.2.3")


def test_import(sample_export, test_repo, snapshot, pinned_version):
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


@pytest.fixture
def claude_export(tmp_path_factory):
    """Create a zip archive from the claude.zip sample export directory."""
    return _prepare_export(SAMPLE_EXPORTS_DIR / "claude.zip", tmp_path_factory.mktemp("export"))


def _edit_metadata(path: Path, **changes) -> None:
    """Change a note's frontmatter as a user would, leaving its body alone."""
    metadata, body = load_frontmatter(path.read_text())
    path.write_text(dump_frontmatter(metadata | changes, body))


def test_import_existing_note_refreshes_importer_metadata(test_repo, claude_export):
    import_(claude_export, test_repo, user="Human")
    imported_file = min((test_repo.root / "chats").glob("**/*.md"))
    _edit_metadata(imported_file, source="stale")

    import_(claude_export, test_repo, user="Human")

    metadata, _ = load_frontmatter(imported_file.read_text())
    assert metadata["source"] == "claude"


def test_import_existing_note_is_rewritten_as_a_fresh_import(test_repo, claude_export):
    """Commonplace owns chats, so re-importing is the backfill: nothing of the old frontmatter survives."""
    import_(claude_export, test_repo, user="Human")
    imported_file = min((test_repo.root / "chats").glob("**/*.md"))
    fresh = imported_file.read_text()
    metadata, body = load_frontmatter(fresh)
    legacy = {k: v for k, v in metadata.items() if k not in ("type", "title", "resource", "generated")}
    imported_file.write_text(dump_frontmatter(legacy | {"rating": 5}, body))

    import_(claude_export, test_repo, user="Human")

    assert imported_file.read_text() == fresh


def test_import_chat_frontmatter_has_okf_type_title_and_generated(sample_export, test_repo, pinned_version):
    import_(sample_export.path, test_repo, user="Human")

    for path in (test_repo.root / "chats").glob("**/*.md"):
        metadata, body = load_frontmatter(path.read_text())
        assert metadata["type"] == "Chat"
        assert body.startswith(f"# {metadata['title']} [created:: ")
        assert metadata["generated"]["by"] == "commonplace/1.2.3"
        last = max(
            datetime.fromisoformat(ts) for ts in re.findall(r"^#+ .* \[created:: ([^\]]+)\]$", body, re.MULTILINE)
        )
        assert datetime.fromisoformat(metadata["generated"]["at"]) == last


RESOURCES = {
    "claude.zip": lambda m: f"https://claude.ai/chat/{m['uuid']}",
    "claude.jsonl.gz": lambda m: f"https://claude.ai/chat/{m['uuid']}",
    "chatgpt.zip": lambda m: f"https://chatgpt.com/c/{m['id']}",
    "gemini.jsonl.gz": lambda m: f"https://gemini.google.com/app/{m['uuid'].removeprefix('c_')}",
    "claude-code.jsonl": lambda m: None,
    "gemini-takeout.zip": lambda m: None,
}


def test_import_chat_resource_is_the_conversation_url_per_source(sample_export, test_repo):
    import_(sample_export.path, test_repo, user="Human")

    for path in (test_repo.root / "chats").glob("**/*.md"):
        metadata, _ = load_frontmatter(path.read_text())
        assert metadata.get("resource") == RESOURCES[sample_export.name](metadata)


AGENTS = {
    "claude.zip": "Claude",
    "claude.jsonl.gz": "Claude",
    "chatgpt.zip": "ChatGPT",
    "gemini.jsonl.gz": "Gemini",
    "claude-code.jsonl": "Claude Code",
    "gemini-takeout.zip": "Gemini",
}


def test_import_speaker_headings_use_the_agent_name(sample_export, test_repo):
    import_(sample_export.path, test_repo, user="Human")

    speakers = {
        speaker
        for path in (test_repo.root / "chats").glob("**/*.md")
        for speaker in re.findall(r"^## (.+?) \[created::", path.read_text(), re.MULTILINE)
        if not speaker.endswith(" call")  # Tool turns
    }
    assert speakers == {"Human", AGENTS[sample_export.name]}


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


CLAUDE_CONVERSATIONS = SAMPLE_EXPORTS_DIR / "claude.zip" / "conversations.json"


def test_can_import_a_stored_conversations_blob():
    """A blob the repo stored must be readable back — provenance that can't be re-read isn't provenance."""
    assert ClaudeExportImporter().can_import(CLAUDE_CONVERSATIONS)


def test_import_a_stored_conversations_blob_yields_logs():
    """The conversations file holds all the importer reads; the zip around it was only packaging."""
    assert ClaudeExportImporter().import_(CLAUDE_CONVERSATIONS)


ZIP_IMPORTERS = {
    "chatgpt.zip": ChatGptImporter,
    "claude.zip": ClaudeExportImporter,
    "gemini-takeout.zip": GeminiTakeoutImporter,
}


@pytest.mark.parametrize("claimed", ZIP_IMPORTERS)
@pytest.mark.parametrize("importer_class", ZIP_IMPORTERS.values(), ids=lambda c: c.__name__)
def test_zip_importer_claims_only_its_own_export(importer_class, claimed, tmp_path, claims):
    export = _prepare_export(SAMPLE_EXPORTS_DIR / claimed, tmp_path)

    assert claims(importer_class(), export) == (ZIP_IMPORTERS[claimed] is importer_class)


def test_zip_contains_file_that_is_not_a_zip_raises(tmp_path):
    """Raising is how a probe says "not mine": autodetect treats any exception as a decline."""
    path = tmp_path / "export.zip"
    path.write_text("not a zip")

    with pytest.raises(BadZipFile):
        zip_contains(path, "conversations.json")


def _takeout(tmp_path: Path, *cells: str) -> Path:
    """A Takeout ZIP whose activity page holds `cells`, each the inner HTML of one content cell."""
    html = "".join(f'<div class="content-cell">{cell}</div>' for cell in cells)
    path = tmp_path / "takeout.zip"
    with ZipFile(path, "w") as zf:
        zf.writestr(GeminiTakeoutImporter().member, f"<html><body>{html}</body></html>")
    return path


def test_takeout_import_groups_exchanges_into_day_logs_in_time_order(tmp_path):
    export = _takeout(
        tmp_path,
        "Prompted second<br>8 Jun 2025, 15:00:00 BST<br><p>two</p>",
        "Prompted next day<br>9 Jun 2025, 09:00:00 BST<br><p>three</p>",
        "Prompted first<br>8 Jun 2025, 13:37:50 BST<br><p>one</p>",
    )

    logs = GeminiTakeoutImporter().import_(export)

    assert [[(e.sender, e.content) for e in log.events] for log in logs] == [
        [(Role.USER, "first"), (Role.ASSISTANT, "one"), (Role.USER, "second"), (Role.ASSISTANT, "two")],
        [(Role.USER, "next day"), (Role.ASSISTANT, "three")],
    ]
    assert logs[0].created == datetime(2025, 6, 8, 12, 37, 50, tzinfo=UTC), "BST is read as an offset, not dropped"


def test_takeout_import_skips_a_cell_that_is_not_a_prompt(tmp_path):
    export = _takeout(
        tmp_path,
        "Used an extension<br>8 Jun 2025, 13:00:00 BST<br><p>not a reply</p>",
        "Prompted hello<br>8 Jun 2025, 13:37:50 BST<br><p>hi</p>",
    )

    [log] = GeminiTakeoutImporter().import_(export)

    assert [e.content for e in log.events] == ["hello", "hi"]


def _claude_code_line(role: str, content, timestamp: str, **message) -> dict:
    return {
        "type": role,
        "sessionId": "session-1",
        "cwd": "/work",
        "timestamp": timestamp,
        "message": {"role": role, "content": content, **message},
    }


def _claude_code_session(tmp_path: Path, *lines: dict) -> Path:
    path = tmp_path / "session.jsonl"
    path.write_text("".join(json.dumps(line) + "\n" for line in lines))
    return path


def test_claude_code_import_pairs_a_tool_result_with_its_call(tmp_path):
    tool_use = {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "ls"}}
    tool_result = {"type": "tool_result", "tool_use_id": "t1", "content": "a.txt"}
    session = _claude_code_session(
        tmp_path,
        _claude_code_line("user", "list the files", "2025-10-01T10:00:00Z"),
        _claude_code_line("assistant", [{"type": "text", "text": "Looking."}, tool_use], "2025-10-01T10:00:01Z"),
        _claude_code_line("user", [tool_result], "2025-10-01T10:00:02Z"),
    )

    [log] = ClaudeCodeImporter().import_(session)

    user, assistant, call = log.events
    assert (user.sender, user.content) == (Role.USER, "list the files")
    assert (assistant.sender, assistant.content) == (Role.ASSISTANT, "Looking.")
    assert (call.tool, call.args, call.output) == ("Bash", {"command": "ls"}, "a.txt")


def test_claude_code_import_titles_a_session_by_its_summary_else_its_id(tmp_path):
    message = _claude_code_line("user", "hi", "2025-10-01T10:00:00Z")
    summary = {"type": "summary", "summary": "A greeting"}

    [untitled] = ClaudeCodeImporter().import_(_claude_code_session(tmp_path, message))
    [titled] = ClaudeCodeImporter().import_(_claude_code_session(tmp_path, summary, message))

    assert (untitled.title, titled.title) == ("session-1", "A greeting")
    assert titled.metadata == {"sessionId": "session-1", "cwd": "/work"}


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


def test_serialize_keeps_unclosed_artifact_code_to_end_of_message():
    """An artifact whose closing tag never arrived still has a code body."""
    content = (
        '<antArtifact identifier="demo" type="application/vnd.ant.code" language="python" title="Demo">\n'
        "x: Callable[[Any], bool]\n"
        "\n"
        "def f(self):\n"
        "    pass\n"
    )
    out = _serialize_message(content)
    assert "x: Callable[[Any], bool]" in out
    assert "\ndef f(self):\n    pass\n" in out


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
