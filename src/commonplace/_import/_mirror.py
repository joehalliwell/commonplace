"""Apply a [[commonplace._import._types.MemoryImporter]]'s snapshot to the repository.

A mirror, not an import: the upstream state is live, rewritten and deleted in
place, so the tree holds what the latest capture listed and git holds the
trajectory. Everything here is the same for every vendor.
"""

from dataclasses import replace
from pathlib import Path, PurePosixPath

from commonplace._import._types import MemoryImporter
from commonplace._logging import logger
from commonplace._repo import Commonplace
from commonplace._types import Note
from commonplace._utils import load_frontmatter
from commonplace._wire import read_header


def mirror_one(path: Path, repo: Commonplace, importer: MemoryImporter, auto_index: bool | None = None) -> None:
    """Land the files the capture read and prune the paths its listing no longer names."""
    tree = importer.tree
    fetched_at = read_header(path).fetched_at
    landed_at = repo.last_commit_time(f"{tree.as_posix()}/")
    if fetched_at and landed_at and fetched_at < landed_at:
        logger.error(f"Not mirroring '{path}': captured {fetched_at}, but '{tree}' was last changed {landed_at}")
        return

    snapshot = importer.snapshot(path)
    # A re-read is a new blob, so rewriting what is already there would change only its provenance.
    notes = [note for note in snapshot.notes if not _landed(repo.root, note)]

    stale: list[Path] = []
    if snapshot.listed is None:
        # Without the complete listing, absence means nothing.
        logger.warning(f"'{path}' has no listing; nothing pruned")
    else:
        root = repo.root / tree
        on_disk = sorted(p.relative_to(root) for p in root.rglob("*") if p.is_file())
        stale = [tree / p for p in on_disk if PurePosixPath(p.as_posix()) not in snapshot.listed]

    # Decided before the blob is stored, so a capture that changes nothing leaves no trace.
    if not notes and not stale:
        logger.info(f"'{tree}' already matches '{path}'")
        return

    provenance = {"source": importer.source, "source_export": repo.store_blob(path).path.as_posix()}
    for note in notes:
        repo.save(replace(note, metadata=note.metadata | provenance))
        logger.info(f"Mirrored '{note.repo_path}'")
    for target in stale:
        repo.remove(target)
        logger.info(f"Pruned '{target}'")

    repo.commit(f"Mirror '{path}' using '{importer.source}' importer", auto_index=auto_index)


def _landed(root: Path, note: Note) -> bool:
    """Whether the working tree already holds this note, whichever capture it was landed from."""
    target = root / note.repo_path.path
    if not target.is_file():
        return False
    metadata, body = load_frontmatter(target.read_text())
    return ({k: v for k, v in metadata.items() if k not in ("source", "source_export")}, body) == (
        note.metadata,
        note.body,
    )
