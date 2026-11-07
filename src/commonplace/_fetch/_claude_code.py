"""Fetch Claude Code's session transcripts from the local machine, where Claude Code keeps them."""

import os
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from commonplace._wire import read_header, write_archive


class ClaudeCodeFetcher:
    """Records each main session transcript changed since the cursor, verbatim, one entry per session."""

    source = "claude-code"

    def __init__(self, root: Path | None = None):
        # Claude Code reads `CLAUDE_CONFIG_DIR` to keep its state somewhere other than `~/.claude`.
        self.root = root or Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")

    def fetch(self, destination: Path, since: datetime | None, previous: Sequence[Path] = ()) -> Path | None:
        # Git's cursor is when the last capture was committed, after it read; a session written in between
        # would wait for its next change. Each capture is stamped before it lists anything, so start from that.
        started = datetime.now(UTC)
        if stamps := [stamp for p in previous if (stamp := read_header(p).fetched_at)]:
            since = max(stamps)
        projects = self.root / "projects"
        # Subagents sit a level down, under `<session>/subagents/`; an orphaned copy repeats a session's id.
        sessions = [p for p in sorted(projects.glob("*/*.jsonl")) if ".orphaned-" not in p.name]
        fresh = [p for p in sessions if since is None or datetime.fromtimestamp(p.stat().st_mtime, UTC) > since]
        if not fresh:
            return None
        entries = (
            {"endpoint": "session", "path": p.relative_to(projects).as_posix(), "response": p.read_text("utf-8")}
            for p in fresh
        )
        return write_archive(destination / f"{self.source}-wire.jsonl.gz", self.source, entries, fetched_at=started)
