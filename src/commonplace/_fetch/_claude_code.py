"""Fetch Claude Code's session transcripts and memory from the local machine, where Claude Code keeps them."""

import json
import os
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from commonplace._wire import read_header, write_archive


def _claude_home(root: Path | None) -> Path:
    """Where Claude Code keeps its state: `root` if given, else `CLAUDE_CONFIG_DIR`, as Claude Code reads it."""
    return root or Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")


class ClaudeCodeFetcher:
    """Records each main session transcript changed since the cursor, verbatim, one entry per session."""

    source = "claude-code"

    def __init__(self, root: Path | None = None):
        self.root = _claude_home(root)

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


class ClaudeCodeMemoryFetcher:
    """Records every project's memory files, and the paths of the projects they belong to, on every run."""

    source = "claude-code-memory"

    def __init__(self, root: Path | None = None):
        self.root = _claude_home(root)

    def fetch(self, destination: Path, since: datetime | None, previous: Sequence[Path] = ()) -> Path | None:
        if not self.root.is_dir():
            return None
        projects = self.root / "projects"
        # A mirror sees a deletion only by its absence from a complete listing, so every run records it all.
        entries = [
            {"endpoint": "projects", "response": json.dumps(self._project_paths())},
            *(
                {"endpoint": "memory", "path": p.relative_to(projects).as_posix(), "response": p.read_text("utf-8")}
                for p in sorted(projects.glob("*/memory/*.md"))
            ),
        ]
        return write_archive(destination / f"{self.source}-wire.jsonl.gz", self.source, entries)

    def _project_paths(self) -> list[str]:
        """The real paths behind `projects/`' directory names, which encode them lossily (`/` and `.` both as `-`).

        Claude Code registers each in `.claude.json`, which also holds account and auth state, so only these are
        recorded. It sits in `CLAUDE_CONFIG_DIR` when that is set, else in the home directory."""
        registry = next((p for p in (self.root / ".claude.json", Path.home() / ".claude.json") if p.is_file()), None)
        return sorted(json.loads(registry.read_text()).get("projects", {})) if registry else []
