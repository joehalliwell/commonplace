"""Importer for the `chatgpt-memory-wire.jsonl.xz` archive produced by [[ChatGptMemoryFetcher]].

Entries are `{"endpoint": "memories"|"summary", "response": ...}`; the summary is a server-sent event stream."""

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from commonplace._import._base import BaseWireImporter
from commonplace._import._types import Snapshot
from commonplace._types import Note, RepoPath
from commonplace._wire import read_entries


class ChatGptMemoryImporter(BaseWireImporter):
    source: str = "chatgpt-memory"
    tree: Path = Path("memory") / "chatgpt"

    def snapshot(self, path: Path, earlier: Sequence[Path] = ()) -> Snapshot:
        notes: list[Note] = []
        summarised = False
        for entry in read_entries(path):
            if entry.get("endpoint") == "memories" and (memories := json.loads(entry["response"])["memories"]):
                # By creation, so an edit changes its own line rather than moving it.
                items = sorted(memories, key=lambda m: m["created_timestamp"])
                bullets = "".join(f"- {m['content'].replace('\n', '\n  ')}\n" for m in items)
                title = "Saved memories"
                repo_path = RepoPath(self.tree / "saved-memories.md")
                notes.append(Note.compose(repo_path, "Memory", title, f"# {title}\n\n{bullets}"))
            elif entry.get("endpoint") == "summary" and (done := _done(entry["response"])) is not None:
                # Each section's id is a stable slug, so it names the file. Follow-ups are prompts, not
                # memory, so a section that is nothing else lands nothing.
                summarised = True
                updated = {"updated_at": done["generatedAtIso"]}
                for s in done["sections"]:
                    if s["description"]:
                        repo_path = RepoPath(self.tree / f"{s['id']}.md")
                        body = f"# {s['title']}\n\n{s['description']}"
                        notes.append(Note.compose(repo_path, "Memory", s["title"], body, updated))
        # Without the summary's `done` event the sections may be partial, so absence proves nothing.
        return Snapshot(notes) if summarised else Snapshot(notes, None)


def _done(stream: str) -> dict[str, Any] | None:
    """The `done` event's data, which restates every section; None if the stream stopped short of it."""
    for event in stream.split("\n\n"):
        fields = dict(line.split(": ", 1) for line in event.splitlines() if ": " in line)
        if fields.get("event") == "done":
            return json.loads(fields["data"])
    return None
