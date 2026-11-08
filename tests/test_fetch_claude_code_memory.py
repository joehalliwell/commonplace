import json
from datetime import UTC, datetime
from pathlib import Path

from commonplace._fetch._claude_code import ClaudeCodeMemoryFetcher
from commonplace._fetch._commands import fetch
from commonplace._import._claude_code_memory import ClaudeCodeMemoryImporter
from commonplace._utils import load_frontmatter
from commonplace._wire import entry_body, read_entries, read_header
from tests.fetching import fetching, owned

MEMORY = """---
name: prefer-dumb-mechanisms
description: "Blunt beats clever"
metadata:
  type: feedback
---

When a check could be smart or blunt, choose blunt.
"""


def _claude_home(tmp_path: Path, projects: dict[str, dict[str, str]], registered: list[str]) -> Path:
    """A `~/.claude` whose `projects/<encoded>/memory/` hold `projects`' files, beside a `.claude.json` registry."""
    home = tmp_path / ".claude"
    for encoded, files in projects.items():
        memory = home / "projects" / encoded / "memory"
        memory.mkdir(parents=True, exist_ok=True)
        for name, text in files.items():
            (memory / name).write_text(text)
    registry = {"oauthAccount": {"emailAddress": "secret@example.com"}, "projects": {p: {} for p in registered}}
    (home / ".claude.json").write_text(json.dumps(registry))
    return home


def _home(tmp_path: Path) -> Path:
    return _claude_home(
        tmp_path,
        {
            "-work-3rd-doux": {"prefer-dumb-mechanisms.md": MEMORY},
            "-work-site-github-io": {"MEMORY.md": "- [Dumb](prefer-dumb-mechanisms.md)\n"},
        },
        registered=["/work/3rd/doux", "/work/site.github.io"],
    )


def test_fetch_records_the_project_paths_and_every_memory_file_verbatim(tmp_path):
    home = _home(tmp_path)
    (home / "projects" / "-work-3rd-doux" / "s1.jsonl").write_text("{}\n")
    (home / "projects" / "-work-3rd-doux" / "memory" / "scratch.txt").write_bytes(b"\x00\xff")

    [archive] = owned(ClaudeCodeMemoryFetcher, root=home).fetch(tmp_path, since=None)

    assert read_header(archive).source == "claude-code-memory"
    entries = list(read_entries(archive))
    assert json.loads(entries[0]["response"]) == ["/work/3rd/doux", "/work/site.github.io"]
    assert [(e["endpoint"], e["path"]) for e in entries[1:]] == [
        ("file", "-work-3rd-doux/memory/prefer-dumb-mechanisms.md"),
        ("file", "-work-3rd-doux/memory/scratch.txt"),
        ("file", "-work-site-github-io/memory/MEMORY.md"),
    ]
    assert [entry_body(e) for e in entries[1:3]] == [MEMORY.encode(), b"\x00\xff"]


def test_snapshot_mirrors_only_markdown(tmp_path):
    home = _home(tmp_path)
    (home / "projects" / "-work-3rd-doux" / "memory" / "scratch.txt").write_text("not a memory\n")
    [archive] = owned(ClaudeCodeMemoryFetcher, root=home).fetch(tmp_path, since=None)

    paths = sorted(n.path.name for n in owned(ClaudeCodeMemoryImporter).snapshot(archive).notes)

    assert paths == ["MEMORY.md", "prefer-dumb-mechanisms.md"]


def test_fetch_records_nothing_else_from_the_registry(tmp_path):
    """`.claude.json` also holds account and auth state; only its project paths are needed."""
    [archive] = owned(ClaudeCodeMemoryFetcher, root=_home(tmp_path)).fetch(tmp_path, since=None)

    assert "secret@example.com" not in json.dumps(list(read_entries(archive)))


def test_fetch_records_the_listing_even_when_nothing_changed(tmp_path):
    """A mirror sees a deletion only by its absence from a complete listing."""
    fetcher = owned(ClaudeCodeMemoryFetcher, root=_home(tmp_path))

    assert fetcher.fetch(tmp_path, since=datetime(2100, 1, 1, tzinfo=UTC)) != []


def test_fetch_without_claude_code_installed_returns_none(tmp_path):
    assert owned(ClaudeCodeMemoryFetcher, root=tmp_path / "absent").fetch(tmp_path, since=None) == []


def test_snapshot_files_each_project_under_the_last_segment_of_its_path(tmp_path):
    [archive] = owned(ClaudeCodeMemoryFetcher, root=_home(tmp_path)).fetch(tmp_path, since=None)

    snapshot = owned(ClaudeCodeMemoryImporter).snapshot(archive)

    assert sorted(n.path.as_posix() for n in snapshot.notes) == [
        "memory/claude-code/doux/prefer-dumb-mechanisms.md",
        "memory/claude-code/site.github.io/MEMORY.md",
    ]
    assert snapshot.unread == frozenset()


def test_snapshot_titles_a_memory_by_its_name_else_its_file(tmp_path):
    [archive] = owned(ClaudeCodeMemoryFetcher, root=_home(tmp_path)).fetch(tmp_path, since=None)

    notes = {n.path.name: n for n in owned(ClaudeCodeMemoryImporter).snapshot(archive).notes}

    assert notes["prefer-dumb-mechanisms.md"].metadata["title"] == "prefer-dumb-mechanisms"
    assert notes["prefer-dumb-mechanisms.md"].metadata["description"] == "Blunt beats clever"
    assert notes["MEMORY.md"].metadata["title"] == "MEMORY"
    assert all(n.metadata["type"] == "Memory" for n in notes.values())


def test_snapshot_an_older_memory_keeps_its_kind_where_newer_ones_hold_it(tmp_path):
    """Older memories carry their kind as a top-level `type`, which the note's own `type: Memory` would overwrite."""
    older = "---\nname: landscape\ntype: project\n---\n\nThe landscape project.\n"
    home = _claude_home(tmp_path, {"-work-landscape": {"landscape.md": older}}, registered=["/work/landscape"])
    [archive] = owned(ClaudeCodeMemoryFetcher, root=home).fetch(tmp_path, since=None)

    [note] = owned(ClaudeCodeMemoryImporter).snapshot(archive).notes

    assert (note.metadata["type"], note.metadata["metadata"]) == ("Memory", {"type": "project"})


def test_snapshot_projects_sharing_a_last_segment_take_the_next_free_name(tmp_path):
    home = _claude_home(
        tmp_path,
        {"-a-notes": {"x.md": "one\n"}, "-b-notes": {"x.md": "two\n"}},
        registered=["/a/notes", "/b/notes"],
    )
    [archive] = owned(ClaudeCodeMemoryFetcher, root=home).fetch(tmp_path, since=None)

    paths = sorted(n.path.as_posix() for n in owned(ClaudeCodeMemoryImporter).snapshot(archive).notes)

    assert paths == ["memory/claude-code/notes-2/x.md", "memory/claude-code/notes/x.md"]


def test_snapshot_a_project_without_memory_takes_no_name(tmp_path):
    home = _claude_home(tmp_path, {"-b-notes": {"x.md": "two\n"}}, registered=["/a/notes", "/b/notes"])
    [archive] = owned(ClaudeCodeMemoryFetcher, root=home).fetch(tmp_path, since=None)

    [note] = owned(ClaudeCodeMemoryImporter).snapshot(archive).notes

    assert note.path.as_posix() == "memory/claude-code/notes/x.md"


def test_snapshot_unregistered_project_keeps_its_directory_name(tmp_path):
    home = _claude_home(tmp_path, {"-gone-project": {"x.md": "one\n"}}, registered=[])
    [archive] = owned(ClaudeCodeMemoryFetcher, root=home).fetch(tmp_path, since=None)

    [note] = owned(ClaudeCodeMemoryImporter).snapshot(archive).notes

    assert note.path.as_posix() == "memory/claude-code/gone-project/x.md"


def test_fetch_command_mirrors_memory_and_prunes_what_was_deleted(test_repo, tmp_path):
    home = _home(tmp_path)
    fetcher = owned(ClaudeCodeMemoryFetcher, root=home)
    fetch(test_repo, sources=fetching(fetcher))
    memory = test_repo.root / "memory" / "claude-code"
    landed = memory / "doux" / "prefer-dumb-mechanisms.md"
    metadata, body = load_frontmatter(landed.read_text())
    assert (metadata["type"], metadata["source"]) == ("Memory", "claude-code-memory")
    assert "choose blunt" in body

    (home / "projects" / "-work-3rd-doux" / "memory" / "prefer-dumb-mechanisms.md").unlink()
    fetch(test_repo, sources=fetching(fetcher))

    assert sorted(p.relative_to(memory).as_posix() for p in memory.rglob("*.md")) == ["site.github.io/MEMORY.md"]


def test_fetch_command_no_index_reaches_the_mirror(test_repo, tmp_path, index_spy):
    """A mirror commits its own capture, so `--no-index` has to be passed down to it."""
    fetch(test_repo, sources=fetching(owned(ClaudeCodeMemoryFetcher, root=_home(tmp_path))))

    assert index_spy == []
