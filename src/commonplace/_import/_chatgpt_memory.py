"""Importer for the `chatgpt-memory-wire.jsonl.gz` archive produced by [[ChatGptMemoryFetcher]].

Entries are `{"endpoint": "memories"|"summary", "response": ...}`; the summary is a server-sent event stream."""

import json
from pathlib import Path, PurePosixPath
from typing import Any

from commonplace._import._base import BaseWireImporter
from commonplace._import._types import Snapshot
from commonplace._wire import read_entries


class ChatGptMemoryImporter(BaseWireImporter):
    source: str = "chatgpt-memory"
    tree: Path = Path("memory") / "chatgpt"
    exhaustive: bool = True

    def snapshot(self, path: Path) -> Snapshot:
        for entry in read_entries(path):
            if entry.get("endpoint") == "summary" and (done := _done(entry["response"])) is not None:
                # Each section's id is a stable slug, so it names the file; follow-ups are prompts, not memory.
                files: dict[PurePosixPath, tuple[dict[str, Any], str]] = {
                    PurePosixPath(f"{s['id']}.md"): (
                        {"updated_at": done["generatedAtIso"]},
                        f"# {s['title']}\n\n{s['description']}",
                    )
                    for s in done["sections"]
                }
                return Snapshot(files, set(files))
        return Snapshot({}, None)


def _done(stream: str) -> dict[str, Any] | None:
    """The `done` event's data, which restates every section; None if the stream stopped short of it."""
    for event in stream.split("\n\n"):
        fields = dict(line.split(": ", 1) for line in event.splitlines() if ": " in line)
        if fields.get("event") == "done":
            return json.loads(fields["data"])
    return None
