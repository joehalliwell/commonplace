"""`show`: everything known about one note, gathered from what already records it.

Each section is a view another command owns: frontmatter (as `ls` reads it), marginalia tags, links both ways,
the commentary in its marginalia, git history, and the search index. Something new to know about a note becomes a
section here rather than a command of its own. One record, two serializations: YAML to read, JSON for scripts;
either gives skills the whole record in one call. The record is a third thing, neither the note nor its
marginalia, so it never takes a note's form; the note itself is read at its path, which `resolve` gives.
"""

from dataclasses import asdict
from pathlib import Path
from typing import Any

import yaml

from commonplace._links import Target
from commonplace._marginalia import links, notes_named, read_marginalia
from commonplace._repo import Commonplace
from commonplace._utils import load_frontmatter

#: The sections after the header, in the order they render.
SECTIONS = ("tags", "links", "commentary", "history", "index")


def show(repo: Commonplace, spec: str, include_hidden: bool = False) -> dict[str, Any]:
    """The record of the note `spec` names; a hidden note is shown when asked for by name, and says so."""
    [note] = notes_named(repo, spec)
    metadata, _ = load_frontmatter((repo.root / note).read_text(errors="replace"))
    marginalia = read_marginalia(repo.root, note)
    # A field the note lacks is left out rather than shown as null.
    header = {field: metadata[field] for field in ("title", "type", "description") if metadata.get(field)}
    return {
        "note": str(Target(note)),
        **header,
        "hidden": "hidden" in marginalia.tags,
        "tags": {"own": list(metadata.get("tags") or []), "marginalia": marginalia.tags},
        "links": [asdict(neighbour) for neighbour in links(repo, spec, include_hidden)],
        "commentary": marginalia.commentary,
        "history": [{"date": day, "subject": subject} for day, subject in repo.history(note)],
        "index": _index_state(repo, note),
    }


def _index_state(repo: Commonplace, note: Path) -> dict[str, Any]:
    """How many chunks the current version has in the index, and whether it's current, stale or not indexed."""
    current = repo.note_version(note)
    index = repo.index
    versions = [path for path in index.get_indexed_paths() if path.path == note]
    if current in versions:
        chunks = sum(stat.num_chunks for stat in index.stats() if stat.repo_path == current)
        return {"state": "current", "chunks": chunks}
    return {"state": "stale" if versions else "not indexed", "chunks": 0}


def select(shown: dict[str, Any], only: list[str] | None = None) -> dict[str, Any]:
    """The record with just the sections asked for (all by default), and always the note it's about."""
    return {key: value for key, value in shown.items() if key not in SECTIONS or not only or key in only}


def render(shown: dict[str, Any], only: list[str] | None = None) -> str:
    """The record as YAML. Not a note: it is about one, so it never borrows a note's form."""
    # Flow style for collections of plain values keeps each link and commit to a line.
    return yaml.safe_dump(
        select(shown, only), sort_keys=False, allow_unicode=True, default_flow_style=None, width=float("inf")
    )
