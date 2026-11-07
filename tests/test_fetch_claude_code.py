import json
import os
from datetime import UTC, datetime
from pathlib import Path

from commonplace._fetch._claude_code import ClaudeCodeFetcher
from commonplace._fetch._commands import fetch
from commonplace._wire import read_entries, read_header

OLD = datetime(2025, 9, 1, tzinfo=UTC)
NEW = datetime(2025, 10, 1, tzinfo=UTC)


def _session(sid: str, prompt: str, timestamp: str) -> str:
    lines = [
        {"type": "mode", "sessionId": sid},
        {"type": "user", "sessionId": sid, "cwd": "/work", "timestamp": timestamp, "message": {"content": prompt}},
        {"type": "ai-title", "aiTitle": prompt.title(), "sessionId": sid},
    ]
    return "".join(json.dumps(line) + "\n" for line in lines)


def _write(path: Path, text: str, modified: datetime) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    os.utime(path, (modified.timestamp(), modified.timestamp()))
    return path


def _claude_home(tmp_path: Path) -> Path:
    """A `~/.claude` with an old and a new session, a subagent and an orphaned copy beside them."""
    home = tmp_path / ".claude"
    project = home / "projects" / "-work"
    _write(project / "s-old.jsonl", _session("s-old", "old work", "2025-09-01T10:00:00Z"), OLD)
    _write(project / "s-new.jsonl", _session("s-new", "new work", "2025-10-01T10:00:00Z"), NEW)
    _write(project / "s-new" / "subagents" / "agent-a1.jsonl", _session("s-new", "survey", "2025-10-01T10:00:01Z"), NEW)
    _write(project / "s-new.orphaned-1-a2.jsonl", _session("s-new", "new work", "2025-10-01T10:00:00Z"), NEW)
    return home


def test_fetch_records_each_main_session_verbatim(tmp_path):
    home = _claude_home(tmp_path)

    archive = ClaudeCodeFetcher(root=home).fetch(tmp_path, since=None)

    assert read_header(archive).source == "claude-code"
    assert [(e["endpoint"], e["path"]) for e in read_entries(archive)] == [
        ("session", "-work/s-new.jsonl"),
        ("session", "-work/s-old.jsonl"),
    ]
    assert next(e["response"] for e in read_entries(archive)) == (home / "projects/-work/s-new.jsonl").read_text()


def test_fetch_incremental_reads_sessions_changed_after_the_cursor(tmp_path):
    archive = ClaudeCodeFetcher(root=_claude_home(tmp_path)).fetch(tmp_path, since=datetime(2025, 9, 15, tzinfo=UTC))

    assert [e["path"] for e in read_entries(archive)] == ["-work/s-new.jsonl"]


def test_fetch_with_nothing_fresh_returns_none(tmp_path):
    fetcher = ClaudeCodeFetcher(root=_claude_home(tmp_path))

    assert fetcher.fetch(tmp_path, since=datetime(2025, 11, 1, tzinfo=UTC)) is None


def test_fetch_without_claude_code_installed_returns_none(tmp_path):
    assert ClaudeCodeFetcher(root=tmp_path / "absent").fetch(tmp_path, since=None) is None


def test_fetch_root_follows_claude_config_dir(tmp_path, monkeypatch):
    """Claude Code reads `CLAUDE_CONFIG_DIR` to move `~/.claude`, so the fetcher follows it there."""
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(_claude_home(tmp_path)))

    archive = ClaudeCodeFetcher().fetch(tmp_path, since=None)

    assert [e["path"] for e in read_entries(archive)] == ["-work/s-new.jsonl", "-work/s-old.jsonl"]


def test_fetch_command_lands_sessions_under_claude_code(test_repo, tmp_path):
    fetch(test_repo, fetchers=[ClaudeCodeFetcher(root=_claude_home(tmp_path))], auto_index=False)

    landed = sorted(p.relative_to(test_repo.root).as_posix() for p in (test_repo.root / "chats").rglob("*.md"))
    assert landed == [
        "chats/claude-code/2025/09/2025-09-01-old-work.md",
        "chats/claude-code/2025/10/2025-10-01-new-work.md",
    ]
