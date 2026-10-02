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
                files[_relative(response["path"])] = with_frontmatter(response["content"], metadata)
        return Snapshot(files, listed)


def _relative(path: str) -> PurePosixPath:
    """Provider paths are rooted at `/`; ours are relative to the tree."""
    return PurePosixPath(path.lstrip("/"))
