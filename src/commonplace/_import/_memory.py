"""Mirror a vendor's assistant memory into `memory/<vendor>/`.

A mirror, not an import: memory is live state that gets rewritten and deleted
upstream, so the tree holds whatever the latest archive listed and git holds
the trajectory. Entries are `{"endpoint": "list"|"read", "path": ..., "response": ...}`.
"""

import json
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

from commonplace._logging import logger
from commonplace._repo import Commonplace
from commonplace._types import Note
from commonplace._wire import read_entries, read_header

#: Wire source -> the vendor directory under `memory/` it mirrors into.
MIRRORED: dict[str, str] = {"claude-memory": "claude"}

#: Fields of a `read` response carried into frontmatter beside `source` and `source_exports`.
PROVENANCE_KEYS = ("category_id", "version", "updated_at")


def memory_tree(source: str) -> Path | None:
    """The directory `source` mirrors into, or `None` if it is not a memory source."""
    vendor = MIRRORED.get(source)
    return Path("memory") / vendor if vendor else None


def mirror_(path: Path, repo: Commonplace, auto_index: bool | None = None) -> None:
    """Land every file the archive read, then prune whatever its listing no longer names."""
    source = read_header(path).source
    assert source is not None
    tree = memory_tree(source)
    assert tree is not None

    source_exports = [repo.store_blob(path).path.as_posix()]
    listed: set[PurePosixPath] | None = None

    for entry in read_entries(path):
        response = json.loads(entry["response"])
        if entry.get("endpoint") == "list":
            listed = {p for item in response["data"] if (p := _relative(item["path"]))}
        elif entry.get("endpoint") == "read":
            rel = _relative(response["path"])
            if rel is None:
                logger.warning(f"Skipping memory with unusable path {response['path']!r}")
                continue
            metadata = {"source": source, "source_exports": source_exports}
            metadata |= {k: response[k] for k in PROVENANCE_KEYS if response.get(k) is not None}
            # `content`, not `parsed`: the latter is the provider's reading of the file.
            content = _with_frontmatter(response["content"], metadata)
            repo.save(Note(repo_path=repo.make_repo_path(tree / rel), content=content))
            logger.info(f"Mirrored '{tree / rel}'")

    if listed is None:
        # Without the complete listing, absence means nothing.
        logger.warning(f"'{path}' has no listing; nothing pruned")
    else:
        root = repo.root / tree
        for existing in sorted(p for p in root.rglob("*") if p.is_file()):
            if PurePosixPath(existing.relative_to(root).as_posix()) not in listed:
                repo.remove(existing.relative_to(repo.root))
                logger.info(f"Pruned '{existing.relative_to(repo.root)}'")

    repo.commit(f"Mirror '{source}' from '{path}'", auto_index=auto_index)


def _relative(path: str) -> PurePosixPath | None:
    """A provider path as one relative to the vendor tree, or `None` if it would not stay inside it."""
    rel = PurePosixPath(path.lstrip("/"))
    if not rel.parts or ".." in rel.parts:
        return None
    return rel


def _with_frontmatter(content: str, metadata: dict[str, Any]) -> str:
    """Add `metadata` to the file's frontmatter textually, so its own lines and body stay byte-for-byte."""
    added = yaml.safe_dump(metadata, sort_keys=False)
    lines = content.split("\n")
    if lines[0].strip() == "---":
        for i, line in enumerate(lines[1:], start=1):
            if line.strip() == "---":
                return "\n".join(lines[:i]) + "\n" + added + "\n".join(lines[i:])
    return f"---\n{added}---\n{content}"
