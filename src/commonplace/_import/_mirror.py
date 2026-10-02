"""Apply a [[commonplace._import._types.Mirror]]'s snapshot to the repository.

A mirror, not an import: the upstream state is live, rewritten and deleted in
place, so the tree holds what the latest capture listed and git holds the
trajectory. Everything here is the same for every vendor.
"""

from pathlib import Path, PurePosixPath
from typing import Any

import yaml

from commonplace._import._types import Mirror
from commonplace._logging import logger
from commonplace._repo import Commonplace
from commonplace._types import Note
from commonplace._wire import read_header


def mirror_one(path: Path, repo: Commonplace, mirror: Mirror, auto_index: bool | None = None) -> None:
    """Land the files the capture read and prune the paths its listing no longer names."""
    tree = mirror.tree
    fetched_at = read_header(path).fetched_at
    landed_at = repo.last_commit_time(f"{tree.as_posix()}/")
    if fetched_at and landed_at and fetched_at < landed_at:
        logger.error(f"Not mirroring '{path}': captured {fetched_at}, but '{tree}' was last changed {landed_at}")
        return

    snapshot = mirror.snapshot(path)
    files = [f for f in snapshot.files if _inside(f.path)]
    for refused in (f for f in snapshot.files if not _inside(f.path)):
        logger.warning(f"Skipping file with unusable path '{refused.path}'")

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

    metadata = {"source": mirror.source, "source_exports": [repo.store_blob(path).path.as_posix()]}
    for file in files:
        target = tree / file.path
        repo.save(Note(repo.make_repo_path(target), _with_frontmatter(file.content, metadata | file.metadata)))
        logger.info(f"Mirrored '{target}'")
    for target in stale:
        repo.remove(target)
        logger.info(f"Pruned '{target}'")

    repo.commit(f"Mirror '{path}' using '{mirror.source}' mirror", auto_index=auto_index)


def _inside(path: PurePosixPath) -> bool:
    """Whether a provider-supplied path stays inside the tree it is relative to."""
    return bool(path.parts) and not path.is_absolute() and ".." not in path.parts


def _with_frontmatter(content: str, metadata: dict[str, Any]) -> str:
    """Add `metadata` to the file's frontmatter textually, so its own lines and body stay byte-for-byte."""
    added = yaml.safe_dump(metadata, sort_keys=False)
    lines = content.split("\n")
    if lines[0].strip() == "---":
        for i, line in enumerate(lines[1:], start=1):
            if line.strip() == "---":
                return "\n".join(lines[:i]) + "\n" + added + "\n".join(lines[i:])
    return f"---\n{added}---\n{content}"
