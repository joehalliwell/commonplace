"""Importer for the `claude-code-memory-wire.jsonl.xz` archive produced by [[ClaudeCodeMemoryFetcher]].

Entries are `{"endpoint": "projects", "response": ...}`, the real paths of Claude Code's projects, then
`{"endpoint": "memory", "path": "<encoded project>/memory/<file>", "response": ...}` for every memory file."""

import json
import re
from collections.abc import Sequence
from pathlib import Path, PurePosixPath

from commonplace._import._base import BaseWireImporter
from commonplace._import._types import Snapshot
from commonplace._types import Note, RepoPath
from commonplace._utils import load_frontmatter
from commonplace._wire import entry_body, read_entries


class ClaudeCodeMemoryImporter(BaseWireImporter):
    def snapshot(self, path: Path, earlier: Sequence[Path] = ()) -> Snapshot:
        entries = list(read_entries(path))
        projects: list[str] = next((json.loads(e["response"]) for e in entries if e["endpoint"] == "projects"), [])
        # The capture holds every file in a memory folder; Claude Code's memories are its Markdown.
        memory = [
            (*e["path"].partition("/memory/")[::2], entry_body(e).decode("utf-8"))
            for e in entries
            if e["endpoint"] == "file" and e["path"].endswith(".md")
        ]
        # Only projects with memory compete for a name, so one without can't push another to `-2`.
        folders = _folders([p for p in projects if _encode(p) in {encoded for encoded, _, _ in memory}])
        notes = []
        for encoded, name, text in memory:
            metadata, body = load_frontmatter(text)
            # Older memories carry their kind as a top-level `type`; newer ones nest it, where `type: Memory` won't
            # overwrite it, so it moves there.
            if kind := metadata.pop("type", None):
                metadata["metadata"] = {"type": kind} | (metadata.get("metadata") or {})
            title = metadata.get("name") or PurePosixPath(name).stem
            repo_path = RepoPath(self.source.tree / folders.get(encoded, encoded.lstrip("-")) / name)
            notes.append(Note.compose(repo_path, "Memory", title, f"# {title}\n\n{body}", metadata))
        # Every capture reads every file, so the listing is complete and nothing goes unread.
        return Snapshot(notes, frozenset())


def _folders(projects: list[str]) -> dict[str, str]:
    """Each project's encoded directory name, as Claude Code writes it, to the last segment of its real path.

    Paths are for people, so a project is named as its folder is; a clash takes the next free `-2`, `-3`."""
    folders: dict[str, str] = {}
    taken: set[str] = set()
    for project in sorted(projects):
        name = base = PurePosixPath(project).name or "root"
        n = 1
        while name in taken:
            n += 1
            name = f"{base}-{n}"
        taken.add(name)
        folders[_encode(project)] = name
    return folders


def _encode(project: str) -> str:
    """A project's directory name under `projects/`, as Claude Code derives it from the project's path."""
    return re.sub(r"[^A-Za-z0-9]", "-", project)
