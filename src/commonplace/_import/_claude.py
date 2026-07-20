"""Importer for the `claude-wire.jsonl.gz` archive produced by [[ClaudeFetcher]].

Each line is a raw Claude API response:

    {"endpoint": "conversations", "response": [...summaries...]}
    {"endpoint": "conversation",  "cid": "...", "response": {...detail...}}
    ...

Text→content wrapping and per-message parsing happens here rather than in
the fetcher, so what's on disk is what Anthropic actually sent."""

import gzip
import json
from pathlib import Path
from typing import Any, Iterable

from rich.progress import track

from commonplace._import._types import EventLog, Message, Role
from commonplace._logging import logger
from commonplace._utils import sniff_gzipped_jsonl, truncate


class ClaudeImporter:
    source: str = "claude"

    def required_paths(self) -> list[str]:
        return []

    def can_import(self, path: Path) -> bool:
        entry = sniff_gzipped_jsonl(path)
        return entry is not None and entry.get("endpoint") in {"conversations", "conversation"}

    def import_(self, path: Path) -> list[EventLog]:
        threads = list(_read_wire(path))
        return [_to_log(thread, self.source) for thread in track(threads)]


def _read_wire(path: Path) -> Iterable[dict[str, Any]]:
    """Yield detail responses from the fetcher's wire log."""
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            entry = json.loads(line)
            if entry.get("endpoint") == "conversation":
                yield entry["response"]


def _to_log(thread: dict[str, Any], source: str) -> EventLog:
    """Shared parse — used by both this importer and ClaudeExportImporter."""
    return EventLog(
        source=source,
        title=thread["name"],
        created=thread["created_at"],
        events=[_to_message(msg) for msg in thread["chat_messages"]],
        metadata={"uuid": thread["uuid"]},
    )


def _to_message(message: dict[str, Any]) -> Message:
    sender = Role.USER if message["sender"] == "human" else Role.ASSISTANT
    created = message["created_at"]

    # Export-ZIP messages carry a populated `content` block list; fetcher-wire
    # messages carry only the flat `text` field. Wrap the latter so both
    # code paths iterate the same structure below.
    contents = message.get("content")
    if not contents:
        contents = [{"type": "text", "text": message.get("text", "")}]

    lines: list[str] = []
    for content in contents:
        type_ = content["type"]
        if type_ == "text":
            lines.append(content["text"])
        else:
            logger.debug(f"Skipping {type_} content block {truncate(str(content))}")
            lines.extend(["> [!NOTE]", f"> Skipped content of type {type_}"])

    return Message(sender=sender, content="\n".join(lines), created=created)
