"""Tests for mirroring vendor assistant memory into `memory/<vendor>/`."""

import gzip
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath

import pytest

from commonplace._import._claude_memory import ClaudeMemoryMirror
from commonplace._import._commands import IMPORTERS, autodetect_importer, import_, landing_tree
from commonplace._import._types import Importer, Mirror
from commonplace._utils import parse_frontmatter
from commonplace._wire import write_archive

EXAMPLE = Path(__file__).parent / "resources" / "wire" / "claude-memory-v3.jsonl.gz"


def _entries(files: dict[str, str], listed: list[str] | None = None) -> list[dict]:
    """Wire entries that read `files` out of a listing of `listed` (default: the same paths)."""
    paths = list(files) if listed is None else listed
    entries = [{"endpoint": "list", "response": json.dumps({"data": [{"path": p} for p in paths]})}]
    for path, content in files.items():
        read = {"path": path, "content": content, "version": "v1", "category_id": "topics", "updated_at": "2026-09-30"}
        entries.append({"endpoint": "read", "path": path, "response": json.dumps(read)})
    return entries


def _archive(tmp_path: Path, files: dict[str, str], listed: list[str] | None = None) -> Path:
    return write_archive(tmp_path / "claude-memory-wire.jsonl.gz", "claude-memory", _entries(files, listed))


def _mirror(repo, archive: Path) -> None:
    import_(archive, repo, user="Human", auto_index=False)


def _tree(repo) -> set[str]:
    root = repo.root / "memory"
    return {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}


def _blobs(repo) -> set[Path]:
    return set((repo.root / ".commonplace" / "blobs").glob("*/*"))


# ---------------------------------------------------------------------------
# The contract: a Mirror is claimed like an Importer but interprets differently.
# ---------------------------------------------------------------------------


def test_claude_memory_mirror_is_a_mirror_not_an_importer():
    mirror = ClaudeMemoryMirror()

    assert isinstance(mirror, Mirror)
    assert not isinstance(mirror, Importer)


def test_every_registered_claimant_is_exactly_one_kind():
    for claimant in IMPORTERS:
        assert isinstance(claimant, Importer) != isinstance(claimant, Mirror), claimant.source


def test_autodetect_example_archive_finds_the_mirror():
    assert isinstance(autodetect_importer(EXAMPLE), ClaudeMemoryMirror)


def test_snapshot_example_archive_interprets_without_a_repo():
    snapshot = ClaudeMemoryMirror().snapshot(EXAMPLE)

    assert snapshot.listed == {PurePosixPath("topics/example.md")}
    [file] = snapshot.files
    assert file.path == PurePosixPath("topics/example.md")
    assert file.content.endswith("Prefers tea. See [[other]].\n")
    assert file.metadata == {"category_id": "topics", "version": "a1b2c3", "updated_at": "2026-09-30T10:00:00Z"}


def test_snapshot_archive_without_listing_has_no_listed_set(tmp_path):
    archive = write_archive(tmp_path / "claude-memory-wire.jsonl.gz", "claude-memory", _entries({"/b.md": "b\n"})[1:])

    assert ClaudeMemoryMirror().snapshot(archive).listed is None


def test_landing_tree_mirror_lands_in_its_own_tree():
    assert landing_tree("claude-memory") == Path("memory/claude")


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

    metadata, _ = parse_frontmatter((test_repo.root / "memory/claude/topics/example.md").read_text())
    assert metadata["source"] == "claude-memory"
    assert metadata["category_id"] == "topics"
    assert metadata["version"] == "a1b2c3"
    assert metadata["updated_at"] == "2026-09-30T10:00:00Z"
    [blob] = metadata["source_exports"]
    assert (test_repo.root / blob).exists()


def test_mirror_file_with_frontmatter_keeps_its_own_lines_verbatim(test_repo, tmp_path):
    content = "---\nname:   Oddly   spaced\ntags: [a,  b]\n---\n\nBody   text.\n"
    _mirror(test_repo, _archive(tmp_path, {"/a.md": content}))

    landed = (test_repo.root / "memory/claude/a.md").read_text()
    assert landed.startswith("---\nname:   Oddly   spaced\ntags: [a,  b]\n")
    assert landed.endswith("---\n\nBody   text.\n")
    metadata, _ = parse_frontmatter(landed)
    assert metadata["tags"] == ["a", "b"]
    assert metadata["source"] == "claude-memory"


def test_mirror_file_without_frontmatter_keeps_body_verbatim(test_repo, tmp_path):
    _mirror(test_repo, _archive(tmp_path, {"/plain.md": "Just a line.\n"}))

    metadata, body = parse_frontmatter((test_repo.root / "memory/claude/plain.md").read_text())
    assert metadata["source"] == "claude-memory"
    assert body == "Just a line.\n"


def test_mirror_path_absent_from_listing_is_pruned(test_repo, tmp_path):
    _mirror(test_repo, _archive(tmp_path, {"/keep.md": "keep\n", "/drop.md": "drop\n"}))
    _mirror(test_repo, _archive(tmp_path, {}, listed=["/keep.md"]))

    assert _tree(test_repo) == {"claude/keep.md"}
    assert "drop.md" not in test_repo.git.head.peel().tree["memory"]["claude"]


def test_mirror_listed_but_unread_path_is_left_alone(test_repo, tmp_path):
    """An incremental fetch reads only what changed; the rest is still listed, so still there."""
    _mirror(test_repo, _archive(tmp_path, {"/a.md": "first\n", "/b.md": "b\n"}))
    _mirror(test_repo, _archive(tmp_path, {"/a.md": "second\n"}, listed=["/a.md", "/b.md"]))

    assert _tree(test_repo) == {"claude/a.md", "claude/b.md"}
    assert "second" in (test_repo.root / "memory/claude/a.md").read_text()


def test_mirror_archive_that_changes_nothing_leaves_no_trace(test_repo, tmp_path):
    """A listing-only archive matching the tree stores no blob and makes no commit."""
    _mirror(test_repo, _archive(tmp_path, {"/a.md": "a\n"}))
    head, blobs = test_repo.git.head.target, _blobs(test_repo)

    _mirror(test_repo, _archive(tmp_path, {}, listed=["/a.md"]))

    assert test_repo.git.head.target == head
    assert _blobs(test_repo) == blobs


def test_mirror_archive_without_listing_prunes_nothing(test_repo, tmp_path):
    _mirror(test_repo, _archive(tmp_path, {"/a.md": "a\n"}))
    unlisted = write_archive(tmp_path / "claude-memory-wire.jsonl.gz", "claude-memory", _entries({"/b.md": "b\n"})[1:])
    _mirror(test_repo, unlisted)

    assert _tree(test_repo) == {"claude/a.md", "claude/b.md"}


def test_mirror_archive_older_than_the_tree_is_refused(test_repo, tmp_path):
    """Replaying a stale capture would prune and overwrite what a later one landed."""
    _mirror(test_repo, _archive(tmp_path, {"/a.md": "current\n", "/b.md": "b\n"}))
    head = test_repo.git.head.target

    stale = tmp_path / "claude-memory-wire.jsonl.gz"
    header = {"wire": "claude-memory", "version": 3, "fetched_at": (datetime.now(UTC) - timedelta(days=1)).isoformat()}
    lines = [header, *_entries({"/a.md": "old\n"})]
    stale.write_bytes(gzip.compress("".join(json.dumps(line) + "\n" for line in lines).encode()))
    _mirror(test_repo, stale)

    assert test_repo.git.head.target == head
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

    assert {test_repo.source(p) for p in test_repo.note_paths()} == {"memory/claude"}
