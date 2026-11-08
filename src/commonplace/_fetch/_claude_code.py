"""Fetch Claude Code's session transcripts and memory from the local machine, where Claude Code keeps them."""

import json
import os
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Self

from commonplace._logging import logger
from commonplace._progress import track
from commonplace._wire import archive_name, file_entry, write_archive

if TYPE_CHECKING:
    from commonplace._config import Config
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


class _ClaudeHome:
    """A fetcher of a source that reads this machine's Claude Code home rather than browsing."""

    def __init__(self, source: "Source", root: Path | None = None):
        self.source = source
        self.root = _claude_home(root)

    @classmethod
    def configured(cls, source: "Source", config: "Config") -> Self:
        """One for `source`, reading this machine's Claude Code home; it browses nothing, so needs no User-Agent."""
        return cls(source)


class ClaudeCodeFetcher(_ClaudeHome):
    """Records each main session transcript changed since the cursor, verbatim, one entry per session."""

    def fetch(self, destination: Path, since: datetime | None, previous: Sequence[Path] = ()) -> list[Path]:
        # Stamped before anything is listed, so a session written while this runs is read by the next fetch.
        started = datetime.now(UTC)
        projects = self.root / "projects"
        # A session is its transcript and everything under `<session>/`, like its subagents and spilled tool results,
        # orphaned copies included. All of it is captured: what makes a note is the importer's call, and whatever a
        # fetch leaves out is gone once Claude Code cleans up.
        fresh = [t for t in sorted(projects.glob("*/*.jsonl")) if since is None or _last_changed(t) > since]
        # One archive per session, so no file outgrows its session and a newer capture of one supersedes it whole.
        logger.info(f"{len(fresh)} sessions changed since {since or 'beginning'}")
        archives = []
        for transcript in track(fresh, f"Fetching {self.source.name}"):
            entries = (file_entry(f, f.relative_to(projects).as_posix()) for f in (transcript, *_folder(transcript)))
            archive = destination / transcript.relative_to(projects).with_suffix("") / archive_name(self.source.name)
            archive.parent.mkdir(parents=True)
            archives.append(write_archive(archive, self.source.name, entries, fetched_at=started))
        return archives


class ClaudeCodeMemoryFetcher(_ClaudeHome):
    """Records every project's memory files, and the paths of the projects they belong to, on every run."""

    def fetch(self, destination: Path, since: datetime | None, previous: Sequence[Path] = ()) -> list[Path]:
        if not self.root.is_dir():
            return []
        projects = self.root / "projects"
        # A mirror sees a deletion only by its absence from a complete listing, so every run records it all.
        memory = sorted(p for p in projects.glob("*/memory/**/*") if p.is_file())
        entries = [
            {"endpoint": "projects", "response": json.dumps(self._project_paths())},
            *(file_entry(p, p.relative_to(projects).as_posix()) for p in memory),
        ]
        return [write_archive(destination / archive_name(self.source.name), self.source.name, entries)]

    def _project_paths(self) -> list[str]:
        """The real paths behind `projects/`' directory names, which encode them lossily (`/` and `.` both as `-`).

        Claude Code registers each in `.claude.json`, which also holds account and auth state, so only these are
        recorded. It sits in `CLAUDE_CONFIG_DIR` when that is set, else in the home directory."""
        registry = next((p for p in (self.root / ".claude.json", Path.home() / ".claude.json") if p.is_file()), None)
        return sorted(json.loads(registry.read_text()).get("projects", {})) if registry else []
