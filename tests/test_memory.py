"""Tests for mirroring agent memory into `memory/<agent>/`."""

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from commonplace._import._chatgpt_memory import ChatGptMemoryImporter
from commonplace._import._claude import ClaudeImporter
from commonplace._import._claude_memory import ClaudeMemoryImporter
from commonplace._import._commands import MIRROR_IMPORTERS, autodetect_importer, import_, landing_tree
from commonplace._import._types import Snapshot
from commonplace._stats import source
from commonplace._types import Note, RepoPath
from commonplace._utils import load_frontmatter
from commonplace._wire import write_archive
from tests.porcelain import git
from tests.test_fetch_chatgpt_memory import SECTIONS, summary_stream

EXAMPLE = Path(__file__).parent / "resources" / "wire" / "claude-memory-v3.jsonl.gz"
CHATGPT_EXAMPLE = Path(__file__).parent / "resources" / "wire" / "chatgpt-memory-v3.jsonl.gz"
CLAUDE_CHATS = Path(__file__).parent / "resources" / "wire" / "claude-v4.jsonl.xz"


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
# The contract: a MirrorImporter is claimed like a ChatImporter but interprets differently.
# ---------------------------------------------------------------------------


def test_import_chat_importer_shaped_like_a_mirror_still_lands_chats(test_repo, monkeypatch):
    """Kind is the registry an importer is in, not the members it happens to have."""

    class Shaped(ClaudeImporter):
        tree = Path("memory") / "claude"

        def snapshot(self, path, earlier=()):
            raise AssertionError("mirrored a chat importer")

    monkeypatch.setattr("commonplace._import._commands.CHAT_IMPORTERS", [Shaped()])

    import_(CLAUDE_CHATS, test_repo, user="Human", auto_index=False)

    assert list((test_repo.root / "chats" / "claude").rglob("*.md"))


def test_autodetect_example_archive_finds_the_memory_importer():
    assert isinstance(autodetect_importer(EXAMPLE, MIRROR_IMPORTERS), ClaudeMemoryImporter)


def test_snapshot_example_archive_interprets_without_a_repo():
    snapshot = ClaudeMemoryImporter().snapshot(EXAMPLE)

    assert snapshot.unread == set()
    [note] = snapshot.notes
    assert note.repo_path == RepoPath(Path("memory/claude/topics/example.md"))
    assert note.body == "# Example\n\n- [stated] Prefers tea. See [[other]]."
    assert note.metadata == {
        "type": "Memory",
        "title": "Example",
        "name": "example",
        "description": "A synthetic memory",
        "sources": ["backfill"],
        "aliases": [],
        "category_id": "topics",
        "version": "a1b2c3d4e5f6",
        "updated_at": "2026-09-30T10:00:00.123456Z",
    }


def test_snapshot_file_without_frontmatter_is_titled_all_the_same(tmp_path):
    [note] = ClaudeMemoryImporter().snapshot(_archive(tmp_path, {"/plain.md": "Just a line.\n"})).notes

    assert note.body == "# Title\n\nJust a line.\n"
    assert note.metadata == {
        "type": "Memory",
        "title": "Title",
        "category_id": "topics",
        "version": "v1",
        "updated_at": "2026-09-30",
    }


def test_snapshot_archive_without_listing_does_not_know_what_is_unread(tmp_path):
    archive = write_archive(tmp_path / "claude-memory-wire.jsonl.gz", "claude-memory", _entries({"/b.md": "b\n"})[1:])

    assert ClaudeMemoryImporter().snapshot(archive).unread is None


def test_snapshot_listed_but_unread_path_is_unread(tmp_path):
    snapshot = ClaudeMemoryImporter().snapshot(_archive(tmp_path, {"/a.md": "a\n"}, listed=["/a.md", "/b.md"]))

    assert snapshot.unread == {Path("memory/claude/b.md")}


def test_landing_tree_memory_source_lands_in_its_own_tree():
    assert landing_tree("claude-memory") == Path("memory/claude")


def test_autodetect_chatgpt_example_archive_finds_its_memory_importer():
    assert isinstance(autodetect_importer(CHATGPT_EXAMPLE, MIRROR_IMPORTERS), ChatGptMemoryImporter)


def test_snapshot_chatgpt_example_archive_lands_the_summary_as_one_file():
    """The example's `dive-deeper` section is only follow-up prompts, so it has nothing to land."""
    snapshot = ChatGptMemoryImporter().snapshot(CHATGPT_EXAMPLE)

    assert snapshot.unread == set()
    [note] = snapshot.notes
    assert note.repo_path == RepoPath(Path("memory/chatgpt/about-you.md"))
    assert note.body == "# About you\n\n## Overview\n\nPrefers tea, and asks for sources.\n"
    assert note.metadata == {"type": "Memory", "title": "About you", "updated_at": "2026-10-03T22:27:53.035594+00:00"}


def test_snapshot_chatgpt_summary_sections_are_headings_in_upstream_order(tmp_path):
    archive = write_archive(
        tmp_path / "chatgpt-memory-wire.jsonl.gz", "chatgpt-memory", [_summary(summary_stream(SECTIONS))]
    )

    [note] = ChatGptMemoryImporter().snapshot(archive).notes
    assert note.body == "# About you\n\n## Overview\n\nPrefers tea.\n\n## Work\n\nWrites software.\n"


def test_snapshot_chatgpt_stream_cut_short_has_no_listed_set(tmp_path):
    """Without the `done` event the summary may be partial, so absence means nothing."""
    stream = summary_stream(SECTIONS).split("event: done")[0]
    archive = write_archive(tmp_path / "chatgpt-memory-wire.jsonl.gz", "chatgpt-memory", [_summary(stream)])

    assert ChatGptMemoryImporter().snapshot(archive) == Snapshot([], None)


def test_snapshot_chatgpt_summary_with_no_sections_lists_nothing(tmp_path):
    archive = write_archive(tmp_path / "chatgpt-memory-wire.jsonl.gz", "chatgpt-memory", [_summary(summary_stream([]))])

    assert ChatGptMemoryImporter().snapshot(archive) == Snapshot([])


def _memories(*items: tuple[str, float]) -> dict:
    """A ChatGPT saved-memories wire entry holding each `(content, created_timestamp)`."""
    memories = [{"id": f"m{i}", "content": c, "created_timestamp": t} for i, (c, t) in enumerate(items)]
    return {"endpoint": "memories", "response": json.dumps({"memories": memories})}


def test_snapshot_chatgpt_saved_memories_land_as_one_file_bulleted_by_creation(tmp_path):
    entries = [
        _memories(("Writes British English.", 2.0), ("Prefers coffee\nto tea.", 1.0)),
        _summary(summary_stream([])),
    ]
    archive = write_archive(tmp_path / "chatgpt-memory-wire.jsonl.gz", "chatgpt-memory", entries)

    [note] = ChatGptMemoryImporter().snapshot(archive).notes
    assert note.repo_path == RepoPath(Path("memory/chatgpt/saved-memories.md"))
    assert note.body == "# Saved memories\n\n- Prefers coffee\n  to tea.\n- Writes British English.\n"


def test_snapshot_chatgpt_saved_memories_land_though_the_summary_stopped_short(tmp_path):
    stream = summary_stream(SECTIONS).split("event: done")[0]
    entries = [_memories(("Prefers coffee.", 1.0)), _summary(stream)]
    archive = write_archive(tmp_path / "chatgpt-memory-wire.jsonl.gz", "chatgpt-memory", entries)

    snapshot = ChatGptMemoryImporter().snapshot(archive)
    assert [n.repo_path.path.name for n in snapshot.notes] == ["saved-memories.md"]
    assert snapshot.unread is None


def test_snapshot_chatgpt_no_saved_memories_lands_no_file(tmp_path):
    archive = write_archive(
        tmp_path / "chatgpt-memory-wire.jsonl.gz", "chatgpt-memory", [_memories(), _summary(summary_stream([]))]
    )

    assert ChatGptMemoryImporter().snapshot(archive) == Snapshot([])


def test_landing_tree_chatgpt_memory_lands_in_its_own_tree():
    assert landing_tree("chatgpt-memory") == Path("memory/chatgpt")


def test_landing_tree_chat_source_lands_under_chats():
    assert landing_tree("claude") == Path("chats/claude")


# ---------------------------------------------------------------------------
# Applying a snapshot to the repository.
# ---------------------------------------------------------------------------


MEMORY_EXAMPLES = sorted(EXAMPLE.parent.glob("*-memory-v*.jsonl.*"))


@pytest.mark.parametrize("archive", MEMORY_EXAMPLES, ids=lambda p: p.name)
def test_mirror_example_archive_renders_as_snapshot(test_repo, archive, snapshot):
    _mirror(test_repo, archive)

    buffer = ""
    for path in sorted((test_repo.root / "memory").glob("**/*.md")):
        buffer += f"<!-- Contents of {path.relative_to(test_repo.root).as_posix()} -->\n"
        buffer += path.read_text(encoding="utf-8") + "\n"

    snapshot.assert_match(buffer, snapshot_name="combined.md")


@pytest.mark.parametrize("archive", MEMORY_EXAMPLES, ids=lambda p: p.name)
def test_mirror_example_archive_leads_every_file_with_okf_type_and_title(test_repo, archive):
    _mirror(test_repo, archive)

    paths = sorted((test_repo.root / "memory").glob("**/*.md"))
    assert paths
    for path in paths:
        metadata, _ = load_frontmatter(path.read_text())
        assert list(metadata)[:2] == ["type", "title"], path
        assert metadata["type"] == "Memory"
        assert metadata["title"]


def test_mirror_file_with_its_own_type_and_title_is_presented_with_ours(test_repo, tmp_path):
    """The vendor's frontmatter survives verbatim in the wire archive; the markdown is our presentation."""
    _mirror(test_repo, _archive(tmp_path, {"/a.md": "---\ntype: user\ntitle: Mine\n---\n\nBody.\n"}))

    metadata, _ = load_frontmatter((test_repo.root / "memory/claude/a.md").read_text())
    assert list(metadata.items())[:2] == [("type", "Memory"), ("title", "Title")]


def test_mirror_file_with_its_own_type_and_title_warns_of_each_override(test_repo, tmp_path, caplog):
    with caplog.at_level(logging.WARNING, logger="commonplace"):
        _mirror(test_repo, _archive(tmp_path, {"/a.md": "---\ntype: user\ntitle: Mine\n---\n\nBody.\n"}))

    overrides = [r.message for r in caplog.records if "overrides" in r.message]
    assert len(overrides) == 2
    assert any("'user'" in m for m in overrides) and any("'Mine'" in m for m in overrides)


def test_mirror_file_whose_type_and_title_match_ours_warns_nothing(test_repo, tmp_path, caplog):
    with caplog.at_level(logging.WARNING, logger="commonplace"):
        _mirror(test_repo, _archive(tmp_path, {"/a.md": "---\ntype: Memory\ntitle: Title\n---\n\nBody.\n"}))

    assert not caplog.records


def test_mirror_file_landed_without_type_gains_it_on_the_next_mirror(test_repo, tmp_path):
    """Files mirrored before `type` existed are otherwise identical, and must not count as landed."""
    old = {"title": "Title", "category_id": "topics", "version": "v1", "updated_at": "2026-09-30"}
    test_repo.save(Note(RepoPath(Path("memory/claude/a.md")), "# Title\n\nBody.\n", old))
    test_repo.commit("Seed", auto_index=False)

    _mirror(test_repo, _archive(tmp_path, {"/a.md": "Body.\n"}))

    metadata, _ = load_frontmatter((test_repo.root / "memory/claude/a.md").read_text())
    assert metadata["type"] == "Memory"


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
    assert (test_repo.root / metadata["source_export"]).exists()


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


@pytest.mark.parametrize("path", ["/../../escape.md", "/a/../../escape.md", "/../chatgpt/theirs.md", ""])
def test_mirror_path_outside_the_tree_fails_the_mirror(test_repo, tmp_path, path):
    with pytest.raises(ValueError):
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

    assert {source(p.path) for p in test_repo.note_paths() if p.path.parts[0] == "memory"} == {"memory/claude"}
