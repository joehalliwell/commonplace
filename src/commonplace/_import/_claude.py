"""Importer for the `claude-wire.jsonl.xz` archive produced by [[ClaudeFetcher]].

Entries are `{"endpoint": "conversations"|"conversation", "cid": ..., "response": ...}`.
Text→content wrapping and per-message parsing live here, not in the fetcher."""

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from commonplace._import._base import BaseWireImporter
from commonplace._import._claude_code import rendered_blocks
from commonplace._import._claude_tasks import run_title, task_of
from commonplace._import._types import EventLog, Message, Role, models_field
from commonplace._logging import logger
from commonplace._progress import track
from commonplace._utils import sniff_gzipped_jsonl, truncate
from commonplace._wire import LEGACY_VERSION, read_entries, read_header

#: Stands in for a message whose text we could not find, mirroring the marker
#: used for content blocks we can't render.
NO_TEXT_NOTE = "> [!NOTE]\n> Message had no recoverable text"


class ClaudeImporter(BaseWireImporter):
    name: str = "Claude"
    id_key: str | None = "uuid"

    def _claims_legacy(self, path: Path) -> bool:
        entry = sniff_gzipped_jsonl(path)
        return entry is not None and entry.get("endpoint") in {"conversations", "conversation"}

    def import_(self, path: Path) -> list[EventLog]:
        threads = list(_read_wire(path))
        logs = [_run(t) if t.get("platform") == "ROUTINE_RUN" else _to_log(t) for t in track(threads)]
        return [log for log in logs if log is not None]


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


def _to_log(thread: dict[str, Any]) -> EventLog:
    """Shared parse — used by both this importer and ClaudeExportImporter."""
    return EventLog(
        title=thread["name"],
        created=thread["created_at"],
        events=[_to_message(msg) for msg in thread["chat_messages"]],
        metadata={
            "uuid": thread["uuid"],
            "resource": f"https://claude.ai/chat/{thread['uuid']}",
            **models_field(_models(thread)),
        },
    )


def _run(thread: dict[str, Any]) -> EventLog | None:
    """A scheduled task's run, read as [[ClaudeTasksImporter]] reads one; None until the reply to its prompt ends."""
    # The prompt is a template, and the scheduled turn its one reply, whose tool calls are working: all stay archived.
    messages = thread["chat_messages"]
    if len(messages) < 2 or not messages[1].get("stop_reason"):
        logger.info(f"Skipping run {thread['uuid']}: no output yet")
        return None
    output = _to_message(messages[1], tools=False)
    log = _to_log(thread | {"chat_messages": messages[2:]})
    task = task_of(thread["name"])
    title = run_title(task, log.created, [output])
    # A run is what a task did, not something said, so it is kept apart from the chats.
    events = [output, *log.events]
    return log.model_copy(
        update={"title": title, "events": events, "folder": "tasks", "metadata": {"task": task, **log.metadata}}
    )


def _models(thread: dict[str, Any]) -> list[str | None]:
    """Messages name no model: `model` is the one in use now, and a safeguard fallback names those before it."""
    fallback = (thread.get("settings") or {}).get("safeguard_fallback") or {}
    hops = [model for hop in fallback.get("hops", []) for model in (hop["from_model"], hop["to_model"])]
    return [*(model["model"] for model in hops), thread.get("model")]


def _to_message(message: dict[str, Any], tools: bool = True) -> Message:
    sender = Role.USER if message["sender"] == "human" else Role.AGENT
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

    # Blocks are shaped as in a Claude Code transcript, so render as its notes do; a turn of only thinking shows empty.
    return Message(sender=sender, content=rendered_blocks(contents, tools) or "", created=created)
