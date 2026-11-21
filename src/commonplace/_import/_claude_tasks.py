"""Importer for the `claude-tasks-wire.jsonl.xz` archive produced by [[ClaudeTasksFetcher]].

Entries are `{"endpoint": "sessions"|"events", "sid": ..., "cursor": ..., "response": ...}`, one per page, for runs
that are Code sessions, whose event payloads are Claude Code transcript lines; then
`{"endpoint": "conversations"|"conversation", "cid": ..., "response": ...}` for runs that are claude.ai chats, as
runs have been since 2026-11-13, whose content blocks are shaped like those lines'."""

import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from commonplace._import._base import BaseWireImporter
from commonplace._import._claude_code import ClaudeCodeImporter
from commonplace._import._types import Event, EventLog, Message, models_field
from commonplace._logging import logger
from commonplace._wire import read_entries

#: The space after `]` keeps a line opening with a markdown link from passing for one.
HEADLINE = re.compile(r"^\[[^\]\n]+\] \S[^\n]*", re.MULTILINE)


class ClaudeTasksImporter(BaseWireImporter):
    name: str = "Claude"
    id_key: str | None = "session_id"

    def import_(self, path: Path) -> list[EventLog]:
        runs: dict[str, dict[str, Any]] = {}
        events: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
        chats: list[dict[str, Any]] = []
        for entry in read_entries(path):
            body = json.loads(entry["response"])
            if entry["endpoint"] == "sessions":
                runs.update((run["id"], run) for run in body["data"])
            elif entry["endpoint"] == "events":
                events[entry["sid"]].extend(body["data"])
            elif entry["endpoint"] == "conversation":
                chats.append(body)
        logs = [*(_to_log(runs[sid], run_events) for sid, run_events in events.items()), *map(_chat_to_log, chats)]
        return [log for log in logs if log is not None]


def _to_log(run: dict[str, Any], run_events: list[dict[str, Any]]) -> EventLog | None:
    """One run as a chat from what its scheduled turn said on, filed by task and start time; None until that ends."""
    ordered = sorted(run_events, key=lambda e: int(e["sequence_num"]))
    end = next((i for i, e in enumerate(ordered) if e["event_type"] == "result"), None)
    if end is None:
        logger.info(f"Skipping run {run['id']}: no output yet")
        return None
    # A follow-up comes from the client, whose payload has no timestamp; the envelope's stands in.
    lines = [{"timestamp": e["created_at"], **e["payload"]} for e in ordered]
    replies = [line for line in lines if line["type"] == "assistant"]
    # The prompt is a template and the scheduled turn's tool calls are working; both stay in the archive.
    # Not `result`, which repeats only the turn's last text: that can be a sign-off after the output proper.
    output = [
        m
        for line in lines[:end]
        if line["type"] == "assistant" and (m := ClaudeCodeImporter._process_event(line, tools=False))
    ]
    follow_ups = [line for line in lines[end + 1 :] if line["type"] in {"user", "assistant"}]
    events: list[Event] = [*output, *(m for line in follow_ups if (m := ClaudeCodeImporter._process_event(line)))]
    events.sort(key=lambda e: e.created)

    created = datetime.fromisoformat(run["created_at"])
    task = _task(run["title"])
    return EventLog(
        title=_title(task, created, output),
        created=created,
        events=events,
        metadata={
            "task": task,
            "session_id": run["id"],
            "trigger_id": run["trigger_id"],
            "resource": f"https://claude.ai/code/{run['id'].replace('cse_', 'session_', 1)}",
            # `<synthetic>` marks a message the harness wrote, not a model.
            **models_field(model for line in replies if (model := line["message"].get("model")) != "<synthetic>"),
            # `is_error`, not `subtype`: an API error can end the turn with `subtype: success`.
            **({"failed": True} if lines[end].get("is_error") else {}),
        },
    )


def _chat_to_log(chat: dict[str, Any]) -> EventLog | None:
    """One run that is a chat, read as a Code session's is; None until the reply to its prompt ends."""
    # The prompt opens the chat, and the scheduled turn is the one reply to it.
    messages = chat["chat_messages"]
    if len(messages) < 2 or not messages[1].get("stop_reason"):
        logger.info(f"Skipping run {chat['uuid']}: no output yet")
        return None
    output = [m for m in [ClaudeCodeImporter._process_event(_as_line(messages[1]), tools=False)] if m]
    replies = [m for message in messages[2:] if (m := ClaudeCodeImporter._process_event(_as_line(message)))]
    created = datetime.fromisoformat(chat["created_at"])
    task = _task(chat["name"])
    return EventLog(
        title=_title(task, created, output),
        created=created,
        events=[*output, *replies],
        metadata={
            "task": task,
            "session_id": chat["uuid"],
            "resource": f"https://claude.ai/chat/{chat['uuid']}",
            **models_field([chat.get("model")]),
        },
    )


def _as_line(message: dict[str, Any]) -> dict[str, Any]:
    """A chat message as the transcript line it would be in a Code session, whose content blocks it shares."""
    kind = "assistant" if message["sender"] == "assistant" else "user"
    return {"type": kind, "timestamp": message["created_at"], "message": {"role": kind, "content": message["content"]}}


def _task(title: str) -> str:
    """The task a run's title names: the app decorates it (a leading "⚡") and may stop, and the slug must not move."""
    return title.lstrip("⚡ ")


def _title(task: str, created: datetime, output: list[Message]) -> str:
    """The headline a prompt can ask a run to open with, like `[AI] What happened`, or else the task and the time."""
    # Narration can precede the headline. The time keeps twice-daily runs of a task from sharing a path.
    headline = HEADLINE.search("\n".join(m.content for m in output))
    return headline[0] if headline else f"{task} {created:%H:%M}"
