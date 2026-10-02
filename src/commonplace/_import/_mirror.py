"""Apply a [[commonplace._import._types.MemoryImporter]]'s snapshot to the repository.

A mirror, not an import: the upstream state is live, rewritten and deleted in
place, so the tree holds what the latest capture listed and git holds the
trajectory. Everything here is the same for every vendor.
"""

from pathlib import Path, PurePosixPath

from commonplace._import._types import MemoryImporter
from commonplace._logging import logger
from commonplace._repo import Commonplace
from commonplace._types import Note
from commonplace._utils import with_frontmatter
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
    files = {p: content for p, content in snapshot.files.items() if _inside(p)}
    for refused in snapshot.files.keys() - files.keys():
        logger.warning(f"Skipping file with unusable path '{refused}'")

    stale: list[Path] = []
    if snapshot.listed is None:
        # Without the complete listing, absence means nothing.
        logger.warning(f"'{path}' has no listing; nothing pruned")
    else:
        root = repo.root / tree
        on_disk = sorted(p.relative_to(root) for p in root.rglob("*") if p.is_file())
        stale = [tree / p for p in on_disk if PurePosixPath(p.as_posix()) not in snapshot.listed]

    # Decided before the blob is stored, so a capture that changes nothing leaves no trace.
    if not files and not stale:
        logger.info(f"'{tree}' already matches '{path}'")
        return

    metadata = {"source": importer.source, "source_exports": [repo.store_blob(path).path.as_posix()]}
    for relative, content in files.items():
        target = tree / relative
        repo.save(Note(repo.make_repo_path(target), with_frontmatter(content, metadata)))
        logger.info(f"Mirrored '{target}'")
    for target in stale:
        repo.remove(target)
        logger.info(f"Pruned '{target}'")

    repo.commit(f"Mirror '{path}' using '{importer.source}' importer", auto_index=auto_index)


def _inside(path: PurePosixPath) -> bool:
    """Whether a provider-supplied path stays inside the tree it is relative to."""
    return bool(path.parts) and not path.is_absolute() and ".." not in path.parts
