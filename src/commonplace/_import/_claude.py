"""Importer for the `claude-wire.jsonl.gz` archive produced by [[ClaudeFetcher]].

Entries are `{"endpoint": "conversations"|"conversation", "cid": ..., "response": ...}`.
Text→content wrapping and per-message parsing live here, not in the fetcher."""

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from rich.progress import track

from commonplace._import._base import BaseWireImporter
from commonplace._import._types import EventLog, Message, Role
from commonplace._logging import logger
from commonplace._utils import sniff_gzipped_jsonl, truncate
from commonplace._wire import LEGACY_VERSION, read_entries, read_header

#: Stands in for a message whose text we could not find, mirroring the marker
#: used for content blocks we can't render.
NO_TEXT_NOTE = "> [!NOTE]\n> Message had no recoverable text"


class ClaudeImporter(BaseWireImporter):
    source: str = "claude"

    def _claims_legacy(self, path: Path) -> bool:
        entry = sniff_gzipped_jsonl(path)
        return entry is not None and entry.get("endpoint") in {"conversations", "conversation"}

    def import_(self, path: Path) -> list[EventLog]:
        threads = list(_read_wire(path))
        return [_to_log(thread, self.source) for thread in track(threads)]


def _read_wire(path: Path) -> Iterable[dict[str, Any]]:
    """Yield detail responses from the fetcher's wire log.

    From v2 `response` is the verbatim body text the server sent; v1 stored it
    already parsed."""
    version = read_header(path).version
    for entry in read_entries(path):
        if entry.get("endpoint") != "conversation":
            continue
        response = entry["response"]
        yield response if version == LEGACY_VERSION else json.loads(response)


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
        if "text" not in message:
            # Neither field. Most likely the provider's shape moved under us:
            # defaulting to "" would import a silently empty message into git,
            # which is worse than a visibly broken one. The archive still holds
            # what was sent, so a fixed importer can re-read it.
            logger.warning(f"Message has no content or text field: {truncate(str(message))}")
            return Message(sender=sender, content=NO_TEXT_NOTE, created=created)
        # An explicit empty string is a message that really is empty.
        contents = [{"type": "text", "text": message["text"]}]

    lines: list[str] = []
    for content in contents:
        type_ = content["type"]
        if type_ == "text":
            lines.append(content["text"])
        else:
            logger.debug(f"Skipping {type_} content block {truncate(str(content))}")
            lines.extend(["> [!NOTE]", f"> Skipped content of type {type_}"])

    return Message(sender=sender, content="\n".join(lines), created=created)
