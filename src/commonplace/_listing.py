"""Folder listings in OKF's index format, built on demand from frontmatter rather than kept as files."""

import json
from pathlib import Path
from typing import Any

from commonplace._repo import Commonplace
from commonplace._types import Note


def listing(repo: Commonplace, folder: Path, fields: list[str], include_hidden: bool = False) -> str:
    """Render a folder's notes, then its subfolders, as an OKF index, with each note's title, description and fields.

    Notes labelled `hidden` are left out unless asked for, and a folder holding nothing else; `tags` are its labels.
    """

    def shown(note: Note) -> bool:
        return include_hidden or not note.hidden

    notes: list[Note] = []
    subfolders: set[str] = set()
    for path in repo.paths(folder):
        rest = path.relative_to(folder)
        if len(rest.parts) > 1:
            if rest.parts[0] not in subfolders and shown(repo.load(path)):
                subfolders.add(rest.parts[0])
        elif path.suffix == ".md" and shown(note := repo.load(path)):
            notes.append(note)
    if not notes and not subfolders:
        raise ValueError(f"Nothing to list in '{folder}'")

    lines = [f"# {folder.as_posix()}", ""]
    for note in notes:
        metadata = dict(note.metadata)
        if "tags" in fields and note.labels:
            metadata["tags"] = note.labels
        entry = f"- [{_one_line(metadata.get('title')) or note.path.stem}]({note.path.name})"
        if description := _one_line(metadata.get("description")):
            entry += f" - {description}"
        lines.append(entry)
        lines += [f"  - {field}: {_render(metadata[field])}" for field in fields if field in metadata]
    lines += [f"- [{name}]({name}/)" for name in sorted(subfolders)]
    return "\n".join(lines) + "\n"


def _one_line(value: Any) -> str:
    """Collapse a scalar's whitespace, so a folded or literal YAML block reads as one line."""
    return "" if value is None else " ".join(str(value).split())


def _render(value: Any) -> str:
    """Show a string as one line and anything else as compact JSON."""
    return _one_line(value) if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
