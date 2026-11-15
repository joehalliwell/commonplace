"""Fetch Claude Code's session transcripts and memory from the local machine, where Claude Code keeps them."""

import json
import os
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from commonplace._fetch._base import BaseFetcher
from commonplace._wire import file_entry

if TYPE_CHECKING:
    from commonplace._types import Source


def _folder(transcript: Path) -> list[Path]:
    """The files under a session's `<session>/` folder, if it has one."""
    return sorted(p for p in transcript.with_suffix("").rglob("*") if p.is_file())


def _last_changed(transcript: Path) -> datetime:
    """When a session last changed: a subagent can finish after its transcript last did."""
    stamps = [transcript.stat().st_mtime, *(p.stat().st_mtime for p in _folder(transcript))]
    return datetime.fromtimestamp(max(stamps), UTC)


def _claude_home(root: Path | None) -> Path:
    """Where Claude Code keeps its state: `root` if given, else `CLAUDE_CONFIG_DIR`, as Claude Code reads it."""
    return root or Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")


class _ClaudeHome(BaseFetcher):
    """Reads this machine's Claude Code home rather than browsing, so uses only the capture."""

    def __init__(self, source: "Source", root: Path | None = None, **browsing: Any):
        super().__init__(source, **browsing)
        self.root = _claude_home(root)


class ClaudeCodeFetcher(_ClaudeHome):
    """Records each session changed since the cursor, file by file and verbatim, in an archive of its own."""

    def fetch(self, destination: Path, since: datetime | None, previous: Sequence[Path] = ()) -> list[Path]:
        self._start()
        projects = self.root / "projects"
        # A session is its transcript and everything under `<session>/`, like its subagents and spilled tool results,
        # orphaned copies included. All of it is captured: what makes a note is the importer's call, and whatever a
        # fetch leaves out is gone once Claude Code cleans up.
        fresh = [t for t in sorted(projects.glob("*/*.jsonl")) if since is None or _last_changed(t) > since]
        # One archive per session, so no file outgrows its session and a newer capture of one supersedes it whole.
        archives: list[Path] = []

        def read(transcript: Path) -> None:
            for file in (transcript, *_folder(transcript)):
                self._log(**file_entry(file, file.relative_to(projects).as_posix()))
            archives.append(self._write_archive(destination / transcript.relative_to(projects).with_suffix("")))

        self._read_fresh(fresh, since, read)
        return archives


class ClaudeCodeMemoryFetcher(_ClaudeHome):
    """Records every project's memory files, and the paths of the projects they belong to, on every run."""

    def fetch(self, destination: Path, since: datetime | None, previous: Sequence[Path] = ()) -> list[Path]:
        if not self.root.is_dir():
            return []
        self._start()
        projects = self.root / "projects"
        self._log(endpoint="projects", response=json.dumps(self._project_paths()))
        # A mirror sees a deletion only by its absence from a complete listing, so every run records it all.
        for file in sorted(p for p in projects.glob("*/memory/**/*") if p.is_file()):
            self._log(**file_entry(file, file.relative_to(projects).as_posix()))
        return [self._write_archive(destination)]

    def _project_paths(self) -> list[str]:
        """The real paths behind `projects/`' directory names, which encode them lossily (`/` and `.` both as `-`).

        Claude Code registers each in `.claude.json`, which also holds account and auth state, so only these are
        recorded. It sits in `CLAUDE_CONFIG_DIR` when that is set, else in the home directory."""
        registry = next((p for p in (self.root / ".claude.json", Path.home() / ".claude.json") if p.is_file()), None)
        return sorted(json.loads(registry.read_text()).get("projects", {})) if registry else []
