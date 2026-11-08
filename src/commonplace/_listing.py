"""Folder listings in OKF's index format, built on demand from frontmatter rather than kept as files."""

import json
from pathlib import Path
from typing import Any

from commonplace._graph import Node
from commonplace._repo import Commonplace
from commonplace._utils import load_frontmatter


def listing(repo: Commonplace, folder: Path, fields: list[str], include_hidden: bool = False) -> str:
    """Render a folder's notes, then its subfolders, as an OKF index, with each note's title, description and fields.

    Notes labelled `hidden` are left out unless asked for, and a folder holding nothing else; `tags` are its labels.
    """

    def shown(node: Node) -> bool:
        return include_hidden or "hidden" not in node.labels

    notes: list[Node] = []
    subfolders: set[str] = set()
    for path in repo.paths():
        try:
            rest = path.relative_to(folder)
        except ValueError:
            continue
        if len(rest.parts) > 1:
            if rest.parts[0] not in subfolders and shown(Node(repo.root, path)):
                subfolders.add(rest.parts[0])
        elif path.suffix == ".md" and shown(node := Node(repo.root, path)):
            notes.append(node)
    if not notes and not subfolders:
        raise ValueError(f"Nothing to list in '{folder}'")

    lines = [f"# {folder.as_posix()}", ""]
    for node in notes:
        metadata, _ = load_frontmatter(node.body)
        if "tags" in fields and node.labels:
            metadata["tags"] = node.labels
        entry = f"- [{_one_line(metadata.get('title')) or node.id.stem}]({node.id.name})"
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
