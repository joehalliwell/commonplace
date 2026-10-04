"""Tests for mirroring vendor assistant memory into `memory/<vendor>/`."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath

import pytest

from commonplace._import._chatgpt_memory import ChatGptMemoryImporter
from commonplace._import._claude_memory import ClaudeMemoryImporter
from commonplace._import._commands import IMPORTERS, autodetect_importer, import_, landing_tree
from commonplace._import._types import ChatImporter, MemoryImporter, Snapshot
from commonplace._utils import load_frontmatter
from commonplace._wire import write_archive
from tests.porcelain import git
from tests.test_fetch_chatgpt_memory import SECTIONS, summary_stream

EXAMPLE = Path(__file__).parent / "resources" / "wire" / "claude-memory-v3.jsonl.gz"
CHATGPT_EXAMPLE = Path(__file__).parent / "resources" / "wire" / "chatgpt-memory-v3.jsonl.gz"


def _entries(files: dict[str, str], listed: list[str] | None = None) -> list[dict]:
    """Wire entries that read `files` out of a listing of `listed` (default: the same paths)."""
    paths = list(files) if listed is None else listed
    entries = [{"endpoint": "list", "response": json.dumps({"data": [{"path": p} for p in paths]})}]
    for path, content in files.items():
        read = {"path": path, "content": content, "version": "v1", "category_id": "topics", "updated_at": "2026-09-30"}
        read["display_name"] = "Title"
        entries.append({"endpoint": "read", "path": path, "response": json.dumps(read)})
    return entries


def _archive(tmp_path: Path, files: dict[str, str], listed: list[str] | None = None) -> Path:
    return write_archive(tmp_path / "claude-memory-wire.jsonl.gz", "claude-memory", _entries(files, listed))


def _summary(stream: str) -> dict:
    """A ChatGPT summary wire entry carrying `stream` as its response."""
    return {"endpoint": "summary", "response": stream}


def _mirror(repo, archive: Path) -> None:
    import_(archive, repo, user="Human", auto_index=False)


def _tree(repo) -> set[str]:
    root = repo.root / "memory"
    return {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file() and p.name != ".gitkeep"}


def _blobs(repo) -> set[Path]:
    return set((repo.root / ".commonplace" / "blobs").glob("*/*"))


# ---------------------------------------------------------------------------
# The contract: a MemoryImporter is claimed like a ChatImporter but interprets differently.
# ---------------------------------------------------------------------------


def test_claude_memory_importer_is_a_memory_importer_not_a_chat_importer():
    importer = ClaudeMemoryImporter()

    assert isinstance(importer, MemoryImporter)
    assert not isinstance(importer, ChatImporter)


def test_every_registered_importer_is_exactly_one_kind():
    for importer in IMPORTERS:
        assert isinstance(importer, ChatImporter) != isinstance(importer, MemoryImporter), importer.source


def test_autodetect_example_archive_finds_the_memory_importer():
    assert isinstance(autodetect_importer(EXAMPLE), ClaudeMemoryImporter)


def test_snapshot_example_archive_interprets_without_a_repo():
    snapshot = ClaudeMemoryImporter().snapshot(EXAMPLE)

    assert snapshot.listed == {PurePosixPath("topics/example.md")}
    [(path, (metadata, body))] = snapshot.files.items()
    assert path == PurePosixPath("topics/example.md")
    assert body == "# Example\n\n- [stated] Prefers tea. See [[other]]."
    assert metadata == {
        "name": "example",
        "description": "A synthetic memory",
        "sources": ["backfill"],
        "aliases": [],
        "category_id": "topics",
        "version": "a1b2c3d4e5f6",
        "updated_at": "2026-09-30T10:00:00.123456Z",
    }


def test_snapshot_file_without_frontmatter_is_titled_all_the_same(tmp_path):
    [(metadata, body)] = (
        ClaudeMemoryImporter().snapshot(_archive(tmp_path, {"/plain.md": "Just a line.\n"})).files.values()
    )

    assert body == "# Title\n\nJust a line.\n"
    assert metadata == {"category_id": "topics", "version": "v1", "updated_at": "2026-09-30"}


def test_snapshot_archive_without_listing_has_no_listed_set(tmp_path):
    archive = write_archive(tmp_path / "claude-memory-wire.jsonl.gz", "claude-memory", _entries({"/b.md": "b\n"})[1:])

    assert ClaudeMemoryImporter().snapshot(archive).listed is None


def test_landing_tree_memory_source_lands_in_its_own_tree():
    assert landing_tree("claude-memory") == Path("memory/claude")


def test_autodetect_chatgpt_example_archive_finds_its_memory_importer():
    assert isinstance(autodetect_importer(CHATGPT_EXAMPLE), ChatGptMemoryImporter)


def test_snapshot_chatgpt_example_archive_lands_a_file_per_section_with_a_description():
    """The example's `dive-deeper` section is only follow-up prompts, so it has nothing to land."""
    snapshot = ChatGptMemoryImporter().snapshot(CHATGPT_EXAMPLE)

    assert snapshot.listed == {PurePosixPath("overview.md")}
    [(path, (metadata, body))] = snapshot.files.items()
    assert path == PurePosixPath("overview.md")
    assert body == "# Overview\n\nPrefers tea, and asks for sources."
    assert metadata == {"updated_at": "2026-10-03T22:27:53.035594+00:00"}


def test_snapshot_chatgpt_stream_cut_short_has_no_listed_set(tmp_path):
    """Without the `done` event the summary may be partial, so absence means nothing."""
    stream = summary_stream(SECTIONS).split("event: done")[0]
    archive = write_archive(tmp_path / "chatgpt-memory-wire.jsonl.gz", "chatgpt-memory", [_summary(stream)])

    assert ChatGptMemoryImporter().snapshot(archive) == Snapshot({}, None)


def test_snapshot_chatgpt_summary_with_no_sections_lists_nothing(tmp_path):
    archive = write_archive(tmp_path / "chatgpt-memory-wire.jsonl.gz", "chatgpt-memory", [_summary(summary_stream([]))])

    assert ChatGptMemoryImporter().snapshot(archive) == Snapshot({}, set())


def test_landing_tree_chatgpt_memory_lands_in_its_own_tree():
    assert landing_tree("chatgpt-memory") == Path("memory/chatgpt")


def test_landing_tree_chat_source_lands_under_chats():
    assert landing_tree("claude") == Path("chats/claude")


# ---------------------------------------------------------------------------
# Applying a snapshot to the repository.
# ---------------------------------------------------------------------------


def test_mirror_example_archive_lands_under_memory_vendor(test_repo):
    _mirror(test_repo, EXAMPLE)

    assert _tree(test_repo) == {"claude/topics/example.md"}


def test_mirror_example_archive_adds_provenance_frontmatter(test_repo):
    _mirror(test_repo, EXAMPLE)

    metadata, body = load_frontmatter((test_repo.root / "memory/claude/topics/example.md").read_text())
    assert body == "# Example\n\n- [stated] Prefers tea. See [[other]]."
    assert metadata["sources"] == ["backfill"]
    assert metadata["source"] == "claude-memory"
    assert metadata["category_id"] == "topics"
    assert metadata["version"] == "a1b2c3d4e5f6"
    assert metadata["updated_at"] == "2026-09-30T10:00:00.123456Z"
    [blob] = metadata["source_exports"]
    assert (test_repo.root / blob).exists()


def test_mirror_file_with_frontmatter_keeps_its_own_values_beside_ours(test_repo, tmp_path):
    content = "---\nname: a\ntags: [x, y]\n---\n\nBody   text.\n"
    _mirror(test_repo, _archive(tmp_path, {"/a.md": content}))

    metadata, body = load_frontmatter((test_repo.root / "memory/claude/a.md").read_text())
    assert (metadata["name"], metadata["tags"]) == ("a", ["x", "y"])
    assert metadata["source"] == "claude-memory"
    assert body == "# Title\n\nBody   text.\n"


def test_mirror_path_absent_from_listing_is_pruned(test_repo, tmp_path):
    _mirror(test_repo, _archive(tmp_path, {"/keep.md": "keep\n", "/drop.md": "drop\n"}))
    _mirror(test_repo, _archive(tmp_path, {}, listed=["/keep.md"]))

    assert _tree(test_repo) == {"claude/keep.md"}
    assert "drop.md" not in git(test_repo.root, "ls-tree", "--name-only", "HEAD:memory/claude").split()


def test_mirror_listed_but_unread_path_is_left_alone(test_repo, tmp_path):
    """An incremental fetch reads only what changed; the rest is still listed, so still there."""
    _mirror(test_repo, _archive(tmp_path, {"/a.md": "first\n", "/b.md": "b\n"}))
    _mirror(test_repo, _archive(tmp_path, {"/a.md": "second\n"}, listed=["/a.md", "/b.md"]))

    assert _tree(test_repo) == {"claude/a.md", "claude/b.md"}
    assert "second" in (test_repo.root / "memory/claude/a.md").read_text()


def test_mirror_archive_that_changes_nothing_leaves_no_trace(test_repo, tmp_path):
    """A listing-only archive matching the tree stores no blob and makes no commit."""
    _mirror(test_repo, _archive(tmp_path, {"/a.md": "a\n"}))
    head, blobs = git(test_repo.root, "rev-parse", "HEAD"), _blobs(test_repo)

    _mirror(test_repo, _archive(tmp_path, {}, listed=["/a.md"]))

    assert git(test_repo.root, "rev-parse", "HEAD") == head
    assert _blobs(test_repo) == blobs


def test_mirror_reread_of_unchanged_files_leaves_no_trace(test_repo, tmp_path, write_jsonl_gz):
    """A re-read is a new archive, hence a new blob, but nothing upstream changed."""
    content = "---\nname: a\n---\nsame\n"
    _mirror(test_repo, _archive(tmp_path, {"/a.md": content}))
    head, blobs = git(test_repo.root, "rev-parse", "HEAD"), _blobs(test_repo)

    header = {"wire": "claude-memory", "version": 3, "fetched_at": datetime.now(UTC).isoformat()}
    reread = write_jsonl_gz(tmp_path / "claude-memory-wire.jsonl.gz", [header, *_entries({"/a.md": content})])
    _mirror(test_repo, reread)

    assert git(test_repo.root, "rev-parse", "HEAD") == head
    assert _blobs(test_repo) == blobs


def test_mirror_archive_without_listing_prunes_nothing(test_repo, tmp_path):
    _mirror(test_repo, _archive(tmp_path, {"/a.md": "a\n"}))
    unlisted = write_archive(tmp_path / "claude-memory-wire.jsonl.gz", "claude-memory", _entries({"/b.md": "b\n"})[1:])
    _mirror(test_repo, unlisted)

    assert _tree(test_repo) == {"claude/a.md", "claude/b.md"}


def test_mirror_archive_older_than_the_tree_is_refused(test_repo, tmp_path, write_jsonl_gz):
    """Replaying a stale capture would prune and overwrite what a later one landed."""
    _mirror(test_repo, _archive(tmp_path, {"/a.md": "current\n", "/b.md": "b\n"}))
    head = git(test_repo.root, "rev-parse", "HEAD")

    header = {"wire": "claude-memory", "version": 3, "fetched_at": (datetime.now(UTC) - timedelta(days=1)).isoformat()}
    stale = write_jsonl_gz(tmp_path / "claude-memory-wire.jsonl.gz", [header, *_entries({"/a.md": "old\n"})])
    _mirror(test_repo, stale)

    assert git(test_repo.root, "rev-parse", "HEAD") == head
    assert "current" in (test_repo.root / "memory/claude/a.md").read_text()
    assert _tree(test_repo) == {"claude/a.md", "claude/b.md"}


@pytest.mark.parametrize("path", ["/../../escape.md", "/a/../../escape.md", ""])
def test_mirror_path_outside_the_tree_is_refused(test_repo, tmp_path, path):
    _mirror(test_repo, _archive(tmp_path, {path: "nope\n"}))

    assert not (test_repo.root / "memory").exists() or _tree(test_repo) == set()
    assert not (test_repo.root / "escape.md").exists()


def test_mirror_leaves_other_vendors_memory_alone(test_repo, tmp_path, make_note):
    test_repo.save(make_note("memory/chatgpt/saved.md", "theirs\n"))
    test_repo.commit("Seed", auto_index=False)

    _mirror(test_repo, _archive(tmp_path, {"/a.md": "a\n"}))

    assert _tree(test_repo) == {"chatgpt/saved.md", "claude/a.md"}


def test_source_memory_note_is_named_for_its_vendor(test_repo):
    _mirror(test_repo, EXAMPLE)

    assert {test_repo.source(p) for p in test_repo.note_paths() if p.path.parts[0] == "memory"} == {"memory/claude"}
