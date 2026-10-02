"""Importer for the `claude-memory-wire.jsonl.gz` archive produced by [[ClaudeMemoryFetcher]].

Entries are `{"endpoint": "list"|"read", "path": ..., "response": ...}`."""

import json
from pathlib import Path, PurePosixPath

from commonplace._import._base import BaseWireImporter
from commonplace._import._types import Snapshot
from commonplace._utils import with_frontmatter
from commonplace._wire import read_entries

#: Fields of a `read` response carried into frontmatter.
PROVENANCE_KEYS = ("category_id", "version", "updated_at")


class ClaudeMemoryImporter(BaseWireImporter):
    source: str = "claude-memory"
    tree: Path = Path("memory") / "claude"

    def snapshot(self, path: Path) -> Snapshot:
        files: dict[PurePosixPath, str] = {}
        listed: set[PurePosixPath] | None = None
        for entry in read_entries(path):
            response = json.loads(entry["response"])
            if entry.get("endpoint") == "list":
                listed = {_relative(item["path"]) for item in response["data"]}
            elif entry.get("endpoint") == "read":
                metadata = {k: response[k] for k in PROVENANCE_KEYS if response.get(k) is not None}
                # `content`, not `parsed`: the latter is the provider's reading of the file.
                content = _with_title(response["content"], response.get("display_name"))
                files[_relative(response["path"])] = with_frontmatter(content, metadata)
        return Snapshot(files, listed)


def _with_title(content: str, title: str | None) -> str:
    """Head the body with `title`, the provider's name for the file, unless it already opens with a heading of its own."""
    lines = content.split("\n")
    start = 0
    if lines[0].strip() == "---":
        start = next((i + 1 for i, line in enumerate(lines[1:], start=1) if line.strip() == "---"), 0)
    opening = next((line for line in lines[start:] if line.strip()), "")
    if not title or opening.startswith("# "):
        return content
    return "\n".join([*lines[:start], f"# {title}", "", *lines[start:]])


def _relative(path: str) -> PurePosixPath:
    """Provider paths are rooted at `/`; ours are relative to the tree."""
    return PurePosixPath(path.lstrip("/"))
