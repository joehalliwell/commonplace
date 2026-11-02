"""Importer for the `keep-wire.jsonl.gz` archive produced by [[KeepFetcher]].

The archive holds every page of one full sync of Keep's `notes/v1/changes`. Notes and lists are root nodes
(`parentId` "root"); their text lives in `LIST_ITEM` children pointing back by `parentId`: one for a note,
one per item for a list. A node not in the trash has the epoch as its `trashed` time. Label names live in
`userInfo.labels`, keyed by `mainId`. Fields are read without defaults where Keep always sends them, so
drift fails loudly.
"""

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from commonplace._import._base import BaseWireImporter
from commonplace._import._mirror import distinct_path
from commonplace._import._types import Snapshot
from commonplace._types import Note, RepoPath
from commonplace._utils import slugify
from commonplace._wire import read_entries

#: Keep's "never": the time a note not in the trash was trashed.
_EPOCH = "1970-01-01T00:00:00.000Z"

#: How many words of an untitled note's first line name its file, and at most how many characters.
_SLUG_WORDS = 6
_SLUG_CHARS = 50


class KeepImporter(BaseWireImporter):
    source: str = "keep"
    tree: Path = Path("notes") / "keep"
    #: A note keeps the path it was first captured at, found by its `id`: retitling in Keep changes its text,
    #: not where it lives, so its marginalia stay attached.
    keeps_first_path: bool = True

    def snapshot(self, path: Path) -> Snapshot:
        nodes: dict[str, dict[str, Any]] = {}
        labels: dict[str, str] = {}
        for entry in read_entries(path):
            page = json.loads(entry["response"])
            nodes |= {node["id"]: node for node in page.get("nodes", [])}
            labels |= {label["mainId"]: label["name"] for label in page.get("userInfo", {}).get("labels", [])}

        items: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for node in nodes.values():
            if node["type"] == "LIST_ITEM" and not _gone(node):
                items[node["parentId"]].append(node)
        roots = [node for node in nodes.values() if node["parentId"] == "root" and not _gone(node)]

        taken: set[Path] = set()
        notes = []
        # Oldest first, so of two notes with the same day and title, the later is the one suffixed.
        for root in sorted(roots, key=lambda node: (node["timestamps"]["created"], node["id"])):
            note = self._note(root, items[root["id"]], labels, taken)
            taken.add(note.repo_path.path)
            notes.append(note)
        return Snapshot(notes, unread=frozenset())

    def _note(
        self, root: dict[str, Any], items: list[dict[str, Any]], labels: dict[str, str], taken: set[Path]
    ) -> Note:
        # Keep shows the highest sortValue first; a note's lone item may have none, where order means nothing.
        items = sorted(items, key=lambda item: int(item.get("sortValue", 0)), reverse=True)
        if root["type"] == "LIST":
            # Keep leaves out `checked` when false.
            text = "".join(f"- [{'x' if item.get('checked') else ' '}] {item['text']}\n" for item in items)
        else:
            text = "\n".join(item["text"] for item in items) + "\n"
        title = root["title"].strip()
        first_line = text.strip().splitlines()[0] if text.strip() else ""
        # An untitled note gets no heading, which would only repeat its first line.
        body = f"# {title}\n\n{text}" if title else text

        created = root["timestamps"]["created"]
        slug = slugify(" ".join((title or first_line).split()[:_SLUG_WORDS]))
        if len(slug) > _SLUG_CHARS:  # One long 'word', like a pasted URL
            slug = slug[:_SLUG_CHARS].rsplit("-", 1)[0]
        slug = slug.strip("-") or "note"
        stem = f"{created[:10]}-{slug}"
        path = self.tree / created[:4] / created[5:7] / f"{stem}.md"
        if path in taken:
            path = distinct_path(path, root["id"])

        metadata = {
            "id": root["id"],
            "created": created,
            "updated": root["timestamps"].get("userEdited", root["timestamps"]["updated"]),
            "labels": [labels[ref["labelId"]] for ref in root.get("labelIds", []) if not _gone(ref)],
            "pinned": root.get("isPinned", False),  # Left out when false
            "archived": root["isArchived"],
        }
        return Note.compose(RepoPath(path), "Note", title or first_line, body, metadata)


def _gone(node: dict[str, Any]) -> bool:
    """Whether a node (or a note's reference to a label) is trashed or deleted."""
    stamps = node.get("timestamps", node)
    return any(stamps.get(field, _EPOCH) != _EPOCH for field in ("trashed", "deleted"))
