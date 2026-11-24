"""`show`: everything known about one note, gathered from what already records it.

Each section is a view another command owns: frontmatter (as `ls` reads it), marginalia tags, links both ways,
the commentary in its marginalia, and the search index; its git history is `commonplace git log --follow`'s. Something
new to know about a note becomes a section here rather than a command of its own. One record, two serializations: YAML to read, JSON for scripts;
either gives skills the whole record in one call. The record is a third thing, neither the note nor its
marginalia, so it never takes a note's form; the note itself is read at its path, which `resolve` gives.
"""

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

from commonplace._links import Target
from commonplace._repo import Commonplace
from commonplace._search._commands import open_index
from commonplace._types import TagFilter

#: The sections after the header, in the order they render.
SECTIONS = ("tags", "links", "commentary", "index")


def show(repo: Commonplace, spec: str, tags: TagFilter = TagFilter()) -> dict[str, Any]:
    """The record of the note `spec` names, whatever its tags, with links to just the notes `tags` admits."""
    [note] = repo.files.resolve(spec)
    node = repo.get(note)
    metadata = node.metadata
    # A field the note lacks is left out rather than shown as null.
    header = {field: metadata[field] for field in ("title", "type", "description") if metadata.get(field)}
    return {
        "note": str(Target(note)),
        **header,
        "tags": {
            "own": list(metadata.get("tags") or []),
            "marginalia": node.marginalia.tags,
        },
        "links": [asdict(neighbour) for neighbour in links(repo, note, tags)],
        "commentary": node.commentary,
        "index": _index_state(repo, note),
    }


def _index_state(repo: Commonplace, note: Path) -> dict[str, Any]:
    """How many chunks the current version has in the index, and whether it's current, stale or not indexed."""
    current = repo.content_ids().get(note, "")
    with open_index(repo) as index:
        indexed = index.chunks_for(note)
    if current in indexed:
        return {"state": "current", "chunks": indexed[current]}
    return {"state": "stale" if indexed else "not indexed", "chunks": 0}


def select(shown: dict[str, Any], only: list[str] | None = None) -> dict[str, Any]:
    """The record with just the sections asked for (all by default), and always the note it's about."""
    return {key: value for key, value in shown.items() if key not in SECTIONS or not only or key in only}


def render(shown: dict[str, Any], only: list[str] | None = None) -> str:
    """The record as YAML. Not a note: it is about one, so it never borrows a note's form."""
    # Flow style for collections of plain values keeps each link and commit to a line.
    return yaml.safe_dump(
        select(shown, only), sort_keys=False, allow_unicode=True, default_flow_style=None, width=float("inf")
    )


@dataclass(frozen=True)
class Neighbour:
    """An edge to or from a note: the node at the other end, rooted, and the line it's written on."""

    direction: str  # "out" from the note, or "in" to it
    other: str
    context: str


def links(repo: Commonplace, note: Path, tags: TagFilter = TagFilter()) -> list[Neighbour]:
    """A note's edges, out then in; those whose other end `tags` doesn't admit are left out."""

    def shown(other: Path) -> bool:
        return tags.admits(repo.get(other).labels)

    node, found = repo.get(note), []
    for edge in repo.edges(note):
        match edge.to:
            case Path() as other if not shown(other):
                continue
            case Path() as other:
                found.append(Neighbour("out", str(Target(other, edge.link.target.partition("#")[2])), node.line(edge)))
            case _:
                found.append(Neighbour("out", edge.link.target, node.line(edge)))
    into = [(source, edge) for source, edge in repo.into(note) if tags.admits(source.labels)]
    return found + [Neighbour("in", str(Target(edge.node)), source.line(edge)) for source, edge in into]
