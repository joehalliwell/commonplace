import json
import os
from datetime import UTC, datetime
from pathlib import Path

from commonplace._fetch._claude_code import ClaudeCodeFetcher
from commonplace._fetch._commands import fetch
from commonplace._wire import archive_names, entry_body, read_entries, read_header
from tests.fetching import fetching, owned
from tests.porcelain import git

OLD = datetime(2025, 9, 1, tzinfo=UTC)
NEW = datetime(2025, 10, 1, tzinfo=UTC)


def _session(sid: str, prompt: str, timestamp: str) -> str:
    lines = [
        {"type": "mode", "sessionId": sid},
        {"type": "user", "sessionId": sid, "cwd": "/work", "timestamp": timestamp, "message": {"content": prompt}},
        {"type": "ai-title", "aiTitle": prompt.title(), "sessionId": sid},
    ]
    return "".join(json.dumps(line) + "\n" for line in lines)


def _write(path: Path, content: str | bytes, modified: datetime) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content.encode() if isinstance(content, str) else content)
    os.utime(path, (modified.timestamp(), modified.timestamp()))
    return path


PNG = b"\x89PNG\r\n\x1a\n\x00\xff"

#: Every file a capture of `_claude_home` since the epoch records, in order.
EVERYTHING = [
    "-work/s-new.jsonl",
    "-work/s-new/subagents/agent-a1.jsonl",
    "-work/s-new/tool-results/b1.bin",
    "-work/s-new/tool-results/t1.txt",
    "-work/s-new.orphaned-1-a2.jsonl",
    "-work/s-old.jsonl",
]


def _claude_home(tmp_path: Path) -> Path:
    """A `~/.claude` with an old and a new session, the new one with a subagent, tool results and an orphaned copy."""
    home = tmp_path / ".claude"
    project = home / "projects" / "-work"
    _write(project / "s-old.jsonl", _session("s-old", "old work", "2025-09-01T10:00:00Z"), OLD)
    _write(project / "s-new.jsonl", _session("s-new", "new work", "2025-10-01T10:00:00Z"), NEW)
    _write(project / "s-new" / "subagents" / "agent-a1.jsonl", _session("s-new", "survey", "2025-10-01T10:00:01Z"), NEW)
    _write(project / "s-new" / "tool-results" / "b1.bin", PNG, NEW)
    _write(project / "s-new" / "tool-results" / "t1.txt", "line one\r\nline two", NEW)
    _write(project / "s-new.orphaned-1-a2.jsonl", _session("s-new", "new work", "2025-10-01T10:00:00Z"), NEW)
    return home


def test_fetch_records_each_session_whole_byte_for_byte(tmp_path):
    """Which of it makes a note is the importer's call; whatever a fetch leaves out is lost once upstream deletes it."""
    home = _claude_home(tmp_path)

    captured = owned(ClaudeCodeFetcher, root=home).fetch(tmp_path, since=None)

    entries = _entries(captured)
    assert sorted((e["endpoint"], e["path"]) for e in entries) == [("file", path) for path in sorted(EVERYTHING)]
    assert all(entry_body(e) == (home / "projects" / e["path"]).read_bytes() for e in entries)


def test_fetch_shows_progress_over_the_sessions_it_reads(tmp_path, monkeypatch):
    """Compressing every session can take minutes; a bar says it hasn't stalled."""
    tracked = []

    def track(items, name):
        tracked.extend(items)
        return tracked

    monkeypatch.setattr("commonplace._fetch._claude_code.track", track)

    owned(ClaudeCodeFetcher, root=_claude_home(tmp_path)).fetch(tmp_path, since=NEW - (NEW - OLD) / 2)

    assert [t.name for t in tracked] == ["s-new.jsonl", "s-new.orphaned-1-a2.jsonl"]


def test_fetch_writes_one_archive_per_session(tmp_path):
    """Files stay as small as one session, and a newer capture of a session supersedes its older one whole."""
    captured = owned(ClaudeCodeFetcher, root=_claude_home(tmp_path)).fetch(tmp_path, since=None)

    archives = {a.parent.relative_to(tmp_path).as_posix(): a for a in captured}
    assert sorted(archives) == ["-work/s-new", "-work/s-new.orphaned-1-a2", "-work/s-old"]
    assert all(read_header(a).source == "claude-code" for a in archives.values())
    assert [e["path"] for e in read_entries(archives["-work/s-new"])] == EVERYTHING[:4]


def test_fetch_incremental_reads_sessions_changed_after_the_cursor(tmp_path):
    captured = owned(ClaudeCodeFetcher, root=_claude_home(tmp_path)).fetch(
        tmp_path, since=datetime(2025, 9, 15, tzinfo=UTC)
    )

    assert _paths(captured) == sorted(EVERYTHING[:-1])


def test_fetch_session_whose_folder_changed_is_read_again(tmp_path):
    """A subagent can finish after its session's transcript last changed."""
    home = _claude_home(tmp_path)
    _write(home / "projects" / "-work" / "s-old" / "subagents" / "agent-a3.jsonl", "{}\n", NEW)

    captured = owned(ClaudeCodeFetcher, root=home).fetch(tmp_path, since=datetime(2025, 9, 15, tzinfo=UTC))

    assert {"-work/s-old.jsonl", "-work/s-old/subagents/agent-a3.jsonl"} <= set(_paths(captured))


def test_fetch_stamps_the_archive_before_listing_sessions(tmp_path, monkeypatch):
    """A session written between listing and stamping would otherwise fall between two fetches."""
    home = _claude_home(tmp_path)
    fetcher = owned(ClaudeCodeFetcher, root=home)
    listed = []
    real_glob = Path.glob

    def glob(self, pattern, **kwargs):
        listed.append(datetime.now(UTC))
        return real_glob(self, pattern, **kwargs)

    monkeypatch.setattr(Path, "glob", glob)
    captured = fetcher.fetch(tmp_path, since=None)
    monkeypatch.undo()

    assert captured
    assert all(read_header(a).fetched_at <= listed[0] for a in captured)


def test_fetch_with_nothing_fresh_returns_none(tmp_path):
    fetcher = owned(ClaudeCodeFetcher, root=_claude_home(tmp_path))

    assert fetcher.fetch(tmp_path, since=datetime(2025, 11, 1, tzinfo=UTC)) == []


def test_fetch_without_claude_code_installed_returns_none(tmp_path):
    assert owned(ClaudeCodeFetcher, root=tmp_path / "absent").fetch(tmp_path, since=None) == []


def test_fetch_root_follows_claude_config_dir(tmp_path, monkeypatch):
    """Claude Code reads `CLAUDE_CONFIG_DIR` to move `~/.claude`, so the fetcher follows it there."""
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(_claude_home(tmp_path)))

    captured = owned(ClaudeCodeFetcher).fetch(tmp_path, since=None)

    assert _paths(captured) == sorted(EVERYTHING)


def test_fetch_command_lands_sessions_under_claude_code_in_one_commit(test_repo, tmp_path):
    """One fetch is one commit, however many sessions it captured, as it is for every source."""
    before = len(git(test_repo.root, "log", "--oneline").splitlines())

    fetch(test_repo, sources=fetching(owned(ClaudeCodeFetcher, root=_claude_home(tmp_path))), auto_index=False)

    landed = sorted(p.relative_to(test_repo.root).as_posix() for p in (test_repo.root / "chats").rglob("*.md"))
    assert landed == [
        "chats/claude-code/2025/09/2025-09-01-old-work.md",
        "chats/claude-code/2025/10/2025-10-01-new-work.md",
    ]
    assert len(git(test_repo.root, "log", "--oneline").splitlines()) == before + 1
    assert len([blob.path for blob in test_repo.blobs(*archive_names("claude-code"))]) == 3


def _entries(captured: list[Path]) -> list[dict]:
    return [e for a in captured for e in read_entries(a)]


def _paths(captured: list[Path]) -> list[str]:
    return sorted(e["path"] for e in _entries(captured))


def test_fetch_command_commit_names_each_stored_archive(test_repo, tmp_path):
    """The temporary directory is gone once the commit lands; the blobs it added are the provenance."""
    fetch(test_repo, sources=fetching(owned(ClaudeCodeFetcher, root=_claude_home(tmp_path))), auto_index=False)

    message = git(test_repo.root, "log", "-1", "--format=%B")
    stored = [blob.path for blob in test_repo.blobs(*archive_names("claude-code"))]
    assert message.startswith("Fetch claude-code: 3 archives")
    assert all(path.as_posix() in message for path in stored)
    assert "/tmp" not in message
