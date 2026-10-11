"""Importer for the `claude-tasks-wire.jsonl.gz` archive produced by [[ClaudeTasksFetcher]].

Entries are `{"endpoint": "sessions"|"events", "sid": ..., "cursor": ..., "response": ...}`, one per page.
Each run is a Code session, so its event payloads are Claude Code transcript lines."""

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from commonplace._import._base import BaseWireImporter
from commonplace._import._claude_code import ClaudeCodeImporter
from commonplace._import._types import Event, EventLog, ToolCall, models_field
from commonplace._wire import read_entries


class ClaudeTasksImporter(BaseWireImporter):
    source: str = "claude-tasks"
    name: str = "Claude"

    def import_(self, path: Path) -> list[EventLog]:
        runs: dict[str, dict[str, Any]] = {}
        events: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
        for entry in read_entries(path):
            page = json.loads(entry["response"])["data"]
            if entry["endpoint"] == "sessions":
                runs.update((run["id"], run) for run in page)
            elif entry["endpoint"] == "events":
                events[entry["sid"]].extend(page)
        return [_to_log(runs[sid], run_events, self.source) for sid, run_events in events.items()]


def _to_log(run: dict[str, Any], run_events: list[dict[str, Any]], source: str) -> EventLog:
    """One run as a chat: its user and assistant events in sequence order, titled by task and start time."""
    # The prompt comes from the client, whose payload has no timestamp; the envelope's stands in.
    ordered = sorted(run_events, key=lambda e: int(e["sequence_num"]))
    lines = [{"timestamp": e["created_at"], **e["payload"]} for e in ordered]
    lines = [line for line in lines if line["type"] in {"user", "assistant"}]
    tool_calls: dict[str, ToolCall] = {}
    events: list[Event] = [m for line in lines if (m := ClaudeCodeImporter._process_event(line, tool_calls))]
    events.extend(tool_calls.values())
    events.sort(key=lambda e: e.created)

    created = datetime.fromisoformat(run["created_at"])
    # The app decorates titles (a leading "⚡") and may stop; the slug must not move when it does.
    task = run["title"].lstrip("⚡ ")
    return EventLog(
        source=source,
        title=f"{task} {created:%H:%M}",
        created=created,
        events=events,
        metadata={
            "session_id": run["id"],
            "trigger_id": run["trigger_id"],
            "resource": f"https://claude.ai/code/{run['id'].replace('cse_', 'session_', 1)}",
            # `<synthetic>` marks a message the harness wrote, not a model.
            **models_field(
                model
                for line in lines
                if line["type"] == "assistant" and (model := line["message"].get("model")) != "<synthetic>"
            ),
        },
    )
