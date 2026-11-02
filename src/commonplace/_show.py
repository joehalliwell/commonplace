"""`show`: everything known about one note, gathered from what already records it.

Each section is a view another command owns: frontmatter (as `ls` reads it), marginalia tags, links both ways,
the sidecar's commentary, git history, and the search index. Something new to know about a note becomes a
section here rather than a command of its own. `--json` gives skills the whole record in one call.
"""

from dataclasses import asdict
from pathlib import Path
from typing import Any

from commonplace._links import Target
from commonplace._marginalia import links, notes_named, read_sidecar
from commonplace._repo import Commonplace
from commonplace._utils import load_frontmatter

#: The sections after the header, in the order they render.
SECTIONS = ("tags", "links", "commentary", "history", "index")


def show(repo: Commonplace, spec: str, include_hidden: bool = False) -> dict[str, Any]:
    """The record of the note `spec` names; a hidden note is shown when asked for by name, and says so."""
    [node] = notes_named(repo, spec)
    metadata, _ = load_frontmatter((repo.root / node).read_text(errors="replace"))
    sidecar = read_sidecar(repo.root, node)
    return {
        "note": str(Target(node)),
        "title": metadata.get("title"),
        "type": metadata.get("type"),
        "description": metadata.get("description"),
        "hidden": "hidden" in sidecar.tags,
        "tags": {"own": list(metadata.get("tags") or []), "marginalia": sidecar.tags},
        "links": [asdict(neighbour) for neighbour in links(repo, spec, include_hidden)],
        "commentary": sidecar.commentary,
        "history": [{"date": day, "subject": subject} for day, subject in repo.history(node)],
        "index": _index_state(repo, node),
    }


def _index_state(repo: Commonplace, node: Path) -> dict[str, Any]:
    """How many chunks the current version has in the index, and whether it's current, stale or not indexed."""
    current = repo.make_repo_path(node)
    index = repo.index
    versions = [path for path in index.get_indexed_paths() if path.path == node]
    if current in versions:
        chunks = sum(stat.num_chunks for stat in index.stats() if stat.repo_path == current)
        return {"state": "current", "chunks": chunks}
    return {"state": "stale" if versions else "not indexed", "chunks": 0}


def render(shown: dict[str, Any], only: list[str] | None = None) -> str:
    """The record as text: a header, then each section asked for (all by default)."""
    header = "  ·  ".join(part for part in (shown["note"], shown["title"], shown["type"]) if part)
    lines = [header]
    if shown["description"]:
        lines.append(shown["description"])
    if shown["hidden"]:
        lines.append("hidden: left out of search and listings")
    for section in only or SECTIONS:
        lines += _SECTION[section](shown)
    return "\n".join(lines) + "\n"


def _tags(shown: dict[str, Any]) -> list[str]:
    own, marginal = shown["tags"]["own"], shown["tags"]["marginalia"]
    return [f"tags      own: {', '.join(own) or '—'}  ·  marginalia: {', '.join(marginal) or '—'}"]


def _links(shown: dict[str, Any]) -> list[str]:
    found = shown["links"]
    outgoing = sum(1 for neighbour in found if neighbour["direction"] == "out")
    lines = [f"links     → {outgoing}  ← {len(found) - outgoing}"]
    for neighbour in found:
        arrow = "→" if neighbour["direction"] == "out" else "←"
        lines.append(f"  {arrow} {neighbour['other']}  {neighbour['context']}")
    return lines


def _commentary(shown: dict[str, Any]) -> list[str]:
    return ["commentary", *(f"  {line}" for line in shown["commentary"])] if shown["commentary"] else []


def _history(shown: dict[str, Any]) -> list[str]:
    history = shown["history"]
    if not history:
        return ["history   not committed"]
    last = history[0]
    return [f"history   {len(history)} commits, last {last['date']} {last['subject']}"]


def _index(shown: dict[str, Any]) -> list[str]:
    index = shown["index"]
    chunks = f"{index['chunks']} chunks, " if index["state"] == "current" else ""
    return [f"index     {chunks}{index['state']}"]


_SECTION = {"tags": _tags, "links": _links, "commentary": _commentary, "history": _history, "index": _index}
