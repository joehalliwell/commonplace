"""Fetch Antigravity's local conversation transcripts, databases, annotations and artefacts."""

import os
import sqlite3
import tempfile
from collections.abc import Sequence
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from commonplace._fetch._base import BaseFetcher
from commonplace._wire import file_entry

if TYPE_CHECKING:
    from commonplace._types import Source

_SUMMARIES_DB = "conversation_summaries.db"
_CONVERSATION_SUFFIXES = (".db", ".pb")


def _antigravity_roots(roots: Sequence[Path] | None) -> list[Path]:
    """Where Antigravity keeps its state: `roots` if given, else `ANTIGRAVITY_HOME`, else both CLI and IDE dirs."""
    if roots is not None:
        return list(roots)
    if env := os.environ.get("ANTIGRAVITY_HOME"):
        return [Path(part) for part in env.split(os.pathsep) if part]
    gemini = Path.home() / ".gemini"
    return [gemini / "antigravity-cli", gemini / "antigravity"]


def _conversation_ids(root: Path) -> list[str]:
    """Every conversation id present anywhere under `root`: `brain/`, `conversations/`, or `annotations/`."""
    ids: set[str] = set()
    if (brain := root / "brain").is_dir():
        ids.update(p.name for p in brain.iterdir() if p.is_dir())
    if (convs := root / "conversations").is_dir():
        ids.update(p.stem for p in convs.iterdir() if p.is_file() and p.suffix in _CONVERSATION_SUFFIXES)
    if (anns := root / "annotations").is_dir():
        ids.update(p.stem for p in anns.iterdir() if p.is_file() and p.suffix == ".pbtxt")
    return sorted(ids)


def _conversation_files(root: Path, cid: str) -> list[Path]:
    """Every file belonging to conversation `cid` under `root`: its brain tree, database/protobuf and annotations."""
    files: list[Path] = []
    if (brain := root / "brain" / cid).is_dir():
        files.extend(sorted(p for p in brain.rglob("*") if p.is_file()))
    for suffix in _CONVERSATION_SUFFIXES:
        if (conv := root / "conversations" / f"{cid}{suffix}").is_file():
            files.append(conv)
    if (ann := root / "annotations" / f"{cid}.pbtxt").is_file():
        files.append(ann)
    return files


def _last_changed(files: Sequence[Path]) -> datetime:
    """Newest mtime across `files`, counting any SQLite `-wal` sidecar where WAL writes land before checkpointing."""
    stamps: list[float] = []
    for path in files:
        stamps.append(path.stat().st_mtime)
        if path.suffix == ".db" and (wal := path.with_name(f"{path.name}-wal")).is_file():
            stamps.append(wal.stat().st_mtime)
    return datetime.fromtimestamp(max(stamps), UTC)


def _sqlite_bytes(path: Path) -> bytes:
    """Snapshot a SQLite database (including committed WAL frames) as standalone bytes, without modifying the source."""
    try:
        with tempfile.TemporaryDirectory() as tmp:
            snap = Path(tmp) / "snapshot.db"
            with (
                closing(sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)) as src,
                closing(sqlite3.connect(snap)) as dst,
            ):
                src.backup(dst)
                # Leave the snapshot in rollback-journal mode so any reader (including `deserialize`) opens it without WAL.
                dst.execute("PRAGMA journal_mode = DELETE")
            return snap.read_bytes()
    except sqlite3.Error:
        return path.read_bytes()


def _record_file(root: Path, path: Path) -> dict[str, Any]:
    """Record `path` under `<root.name>/<rel>`, snapshotting SQLite `.db` files cleanly from WAL."""
    name = f"{root.name}/{path.relative_to(root).as_posix()}"
    return file_entry(path, name, content=_sqlite_bytes(path) if path.suffix == ".db" else None)


class AntigravityFetcher(BaseFetcher):
    """Records each local Antigravity conversation changed since the cursor, verbatim, with summaries once per fetch."""

    def __init__(
        self, source: "Source", root: Path | None = None, roots: Sequence[Path] | None = None, **browsing: Any
    ):
        super().__init__(source, **browsing)
        self.roots = _antigravity_roots([root] if root is not None else roots)

    def fetch(self, destination: Path, since: datetime | None, previous: Sequence[Path] = ()) -> list[Path]:
        self._start()
        present = [root for root in self.roots if root.is_dir()]
        if not present:
            return []
        # Capture every conversation's full brain tree, database/protobuf and annotations verbatim across both app-data
        # dirs; what makes a note is the importer's call.
        fresh = [
            (root, cid, files)
            for root in present
            for cid in _conversation_ids(root)
            if (files := _conversation_files(root, cid)) and (since is None or _last_changed(files) > since)
        ]
        if not fresh:
            return []

        def read(item: tuple[Path, str, list[Path]]) -> None:
            root, _, files = item
            for file in files:
                self._log(**_record_file(root, file))

        self._read_fresh(fresh, since, read)
        # Capture `conversation_summaries.db` once per fetch (per app dir that has it), alongside the fresh conversations
        # so the archive is self-contained for both `fetch` and `doctor --render`.
        for root in present:
            if (summaries := root / _SUMMARIES_DB).is_file():
                self._log(**_record_file(root, summaries))
        return [self._write_archive(destination)]
