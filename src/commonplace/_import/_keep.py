"""Importer for the `keep-wire.jsonl.xz` archives produced by [[KeepFetcher]].

An archive holds every page of one sync of Keep's `notes/v1/changes`: a full sync if its first request named
no version, otherwise a change set since the version it named. Keep's state is the last full sync with every
change set since replayed on it, node by node; a note trashed or deleted arrives as a change like any other.
Notes and lists are root nodes
(`parentId` "root"); their text lives in `LIST_ITEM` children pointing back by `parentId`: one for a note,
one per item for a list. A node not in the trash has the epoch as its `trashed` time. Label names live in
`userInfo.labels`, keyed by `mainId`. Fields are read without defaults where Keep always sends them, so
drift fails loudly.
"""

import json
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from commonplace._import._base import BaseWireImporter
from commonplace._import._types import Snapshot
from commonplace._types import Note
from commonplace._utils import slugify
from commonplace._wire import read_entries

#: Keep's "never": the time a note not in the trash was trashed.
_EPOCH = "1970-01-01T00:00:00.000Z"

#: How many words of an untitled note's first line name its file, and at most how many characters.
_SLUG_WORDS = 6
_SLUG_CHARS = 50


class KeepImporter(BaseWireImporter):
    #: A note keeps the path it was first captured at, found by its `id`: retitling in Keep changes its text,
    #: not where it lives, so its marginalia stay attached.
    id_key: str | None = "id"

    def snapshot(self, path: Path, earlier: Sequence[Path] = ()) -> Snapshot:
        """Keep's whole state as of `path`: the last full sync up to it, with every change set since replayed."""
        chain = since_last_full([*earlier, path])
        if not is_full_sync(chain[0]):
            raise ValueError(f"'{path}' is a change set, and no full sync before it was given to replay it on")
        nodes: dict[str, dict[str, Any]] = {}
        labels: dict[str, str] = {}
        for entry in (entry for archive in chain for entry in read_entries(archive)):
            page = json.loads(entry["response"])
            nodes |= {node["id"]: node for node in page.get("nodes", [])}
            labels |= {label["mainId"]: label["name"] for label in page.get("userInfo", {}).get("labels", [])}

        items: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for node in nodes.values():
            if node["type"] == "LIST_ITEM" and not _gone(node):
                items[node["parentId"]].append(node)
        roots = [node for node in nodes.values() if node["parentId"] == "root" and not _gone(node)]

        # Oldest first, so of two notes with the same day and title, the later is the one the mirror suffixes.
        roots.sort(key=lambda node: (node["timestamps"]["created"], node["id"]))
        return Snapshot([self._note(root, items[root["id"]], labels) for root in roots], unread=frozenset())

    def _note(self, root: dict[str, Any], items: list[dict[str, Any]], labels: dict[str, str]) -> Note:
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
        path = self.source.tree / created[:4] / created[5:7] / f"{stem}.md"

        # Keep's labels are what the note is, so frontmatter, under OKF's `tags`, the word marginalia use too.
        tags = [labels[ref["labelId"]] for ref in root.get("labelIds", []) if not _gone(ref)]
        metadata = {
            "id": root["id"],
            "created": created,
            "updated": root["timestamps"].get("userEdited", root["timestamps"]["updated"]),
            **({"tags": tags} if tags else {}),
            "pinned": root.get("isPinned", False),  # Left out when false
            "archived": root["isArchived"],
        }
        return Note.compose(Path(path), "Note", title or first_line, body, metadata)


def is_full_sync(archive: Path) -> bool:
    """Whether the archive's first request named no version, so it holds the whole state, not a change set."""
    first = next(read_entries(archive))
    return first["targetVersion"] is None


def since_last_full(archives: Sequence[Path]) -> list[Path]:
    """The archives from the last full sync on, which are all a replay needs; all of them if none is full."""
    starts = [i for i, archive in enumerate(archives) if is_full_sync(archive)]
    return list(archives[starts[-1] :] if starts else archives)


def last_version(archive: Path) -> str:
    """The version Keep's state had reached when the archive's last page was written: the next sync starts there."""
    *_, entry = read_entries(archive)
    return json.loads(entry["response"])["toVersion"]


def _gone(node: dict[str, Any]) -> bool:
    """Whether a node (or a note's reference to a label) is trashed or deleted."""
    stamps = node.get("timestamps", node)
    return any(stamps.get(field, _EPOCH) != _EPOCH for field in ("trashed", "deleted"))
