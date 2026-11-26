"""Fetch Antigravity's local conversation transcripts and artefacts from where Antigravity keeps them."""

import os
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from commonplace._fetch._base import BaseFetcher
from commonplace._wire import file_entry

if TYPE_CHECKING:
    from commonplace._types import Source

_LOGS = Path(".system_generated") / "logs"
_TRANSCRIPTS = (_LOGS / "transcript_full.jsonl", _LOGS / "transcript.jsonl")


def _files(conversation: Path) -> list[Path]:
    """Every file under a conversation's brain directory, in order."""
    return sorted(p for p in conversation.rglob("*") if p.is_file())


def _has_transcript(conversation: Path) -> bool:
    """Whether `conversation` has a JSONL transcript on disk to capture."""
    return any((conversation / rel).is_file() for rel in _TRANSCRIPTS)


def _last_changed(files: Sequence[Path]) -> datetime:
    """When a conversation last changed: an artefact or step output can be written after the transcript."""
    return datetime.fromtimestamp(max(p.stat().st_mtime for p in files), UTC)


def _antigravity_home(root: Path | None) -> Path:
    """Where Antigravity keeps its state: `root` if given, else `ANTIGRAVITY_HOME`, else `~/.gemini/antigravity-cli`."""
    return root or Path(os.environ.get("ANTIGRAVITY_HOME") or Path.home() / ".gemini" / "antigravity-cli")


class AntigravityFetcher(BaseFetcher):
    """Records each local Antigravity conversation changed since the cursor, file by file and verbatim."""

    def __init__(self, source: "Source", root: Path | None = None, **browsing: Any):
        super().__init__(source, **browsing)
        self.root = _antigravity_home(root)

    def fetch(self, destination: Path, since: datetime | None, previous: Sequence[Path] = ()) -> list[Path]:
        self._start()
        brain = self.root / "brain"
        if not brain.is_dir():
            return []
        # A conversation is its transcript and everything beside it in `brain/<id>/`: artefacts, scratch files,
        # uploads and full step outputs. All of it is captured verbatim; what makes a note is the importer's call.
        conversations = [
            (conv, files)
            for conv in sorted(brain.iterdir())
            if conv.is_dir() and _has_transcript(conv) and (files := _files(conv))
        ]
        fresh = [(conv, files) for conv, files in conversations if since is None or _last_changed(files) > since]
        # One archive per conversation, so no file outgrows its session and a newer capture supersedes it whole.
        archives: list[Path] = []

        def read(item: tuple[Path, list[Path]]) -> None:
            conv, files = item
            for file in files:
                self._log(**file_entry(file, file.relative_to(brain).as_posix()))
            archives.append(self._write_archive(destination / conv.name))

        self._read_fresh(fresh, since, read)
        return archives
