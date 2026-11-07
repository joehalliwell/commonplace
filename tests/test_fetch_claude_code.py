import json
import os
from datetime import UTC, datetime
from pathlib import Path

from commonplace._fetch._claude_code import ClaudeCodeFetcher
from commonplace._fetch._commands import fetch
from commonplace._wire import entry_body, read_entries, read_header, write_archive

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

    archive = ClaudeCodeFetcher(root=home).fetch(tmp_path, since=None)

    assert read_header(archive).source == "claude-code"
    entries = list(read_entries(archive))
    assert [(e["endpoint"], e["path"]) for e in entries] == [("file", path) for path in EVERYTHING]
    assert all(entry_body(e) == (home / "projects" / e["path"]).read_bytes() for e in entries)


def test_fetch_incremental_reads_sessions_changed_after_the_cursor(tmp_path):
    archive = ClaudeCodeFetcher(root=_claude_home(tmp_path)).fetch(tmp_path, since=datetime(2025, 9, 15, tzinfo=UTC))

    assert [e["path"] for e in read_entries(archive)] == EVERYTHING[:-1]


def test_fetch_session_whose_folder_changed_is_read_again(tmp_path):
    """A subagent can finish after its session's transcript last changed."""
    home = _claude_home(tmp_path)
    _write(home / "projects" / "-work" / "s-old" / "subagents" / "agent-a3.jsonl", "{}\n", NEW)

    archive = ClaudeCodeFetcher(root=home).fetch(tmp_path, since=datetime(2025, 9, 15, tzinfo=UTC))

    assert [e["path"] for e in read_entries(archive)][-2:] == [
        "-work/s-old.jsonl",
        "-work/s-old/subagents/agent-a3.jsonl",
    ]


def test_fetch_session_changed_during_the_previous_fetch_is_read_again(tmp_path):
    """Git's cursor is the previous fetch's commit, made after it read; its archive is stamped before."""
    home = _claude_home(tmp_path)
    previous = write_archive(
        tmp_path / "previous.jsonl.gz", "claude-code", [], fetched_at=datetime(2025, 9, 30, tzinfo=UTC)
    )

    archive = ClaudeCodeFetcher(root=home).fetch(tmp_path, since=datetime(2025, 10, 2, tzinfo=UTC), previous=[previous])

    assert [e["path"] for e in read_entries(archive)] == EVERYTHING[:-1]


def test_fetch_stamps_the_archive_before_listing_sessions(tmp_path, monkeypatch):
    """A session written between listing and stamping would otherwise fall between two fetches."""
    home = _claude_home(tmp_path)
    fetcher = ClaudeCodeFetcher(root=home)
    listed = []
    real_glob = Path.glob

    def glob(self, pattern, **kwargs):
        listed.append(datetime.now(UTC))
        return real_glob(self, pattern, **kwargs)

    monkeypatch.setattr(Path, "glob", glob)
    archive = fetcher.fetch(tmp_path, since=None)

    assert read_header(archive).fetched_at <= listed[0]


def test_fetch_with_nothing_fresh_returns_none(tmp_path):
    fetcher = ClaudeCodeFetcher(root=_claude_home(tmp_path))

    assert fetcher.fetch(tmp_path, since=datetime(2025, 11, 1, tzinfo=UTC)) is None


def test_fetch_without_claude_code_installed_returns_none(tmp_path):
    assert ClaudeCodeFetcher(root=tmp_path / "absent").fetch(tmp_path, since=None) is None


def test_fetch_root_follows_claude_config_dir(tmp_path, monkeypatch):
    """Claude Code reads `CLAUDE_CONFIG_DIR` to move `~/.claude`, so the fetcher follows it there."""
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(_claude_home(tmp_path)))

    archive = ClaudeCodeFetcher().fetch(tmp_path, since=None)

    assert [e["path"] for e in read_entries(archive)] == EVERYTHING


def test_fetch_command_lands_sessions_under_claude_code(test_repo, tmp_path):
    fetch(test_repo, fetchers=[ClaudeCodeFetcher(root=_claude_home(tmp_path))], auto_index=False)

    landed = sorted(p.relative_to(test_repo.root).as_posix() for p in (test_repo.root / "chats").rglob("*.md"))
    assert landed == [
        "chats/claude-code/2025/09/2025-09-01-old-work.md",
        "chats/claude-code/2025/10/2025-10-01-new-work.md",
    ]
