"""Importer for the `antigravity-wire.jsonl.xz` archive [[AntigravityFetcher]] records.

Each entry is `{"endpoint": "file", "path": "<cid>/...", "response": ...}`, recording every file under a
conversation's `brain/<cid>/` directory verbatim. Notes are rendered from `.system_generated/logs/transcript_full.jsonl`
(falling back to `transcript.jsonl` if full is absent); thinking, tool outputs, harness messages and artefacts stay in
the archive.
"""

import json
import re
from datetime import datetime
from pathlib import Path, PurePosixPath
from textwrap import shorten
from typing import Any

from commonplace._import._base import BaseWireImporter
from commonplace._import._claude_code import joined, merged, records, tool_line
from commonplace._import._types import EventLog, Message, Role, models_field
from commonplace._logging import logger
from commonplace._wire import entry_body, read_entries

_FULL_TRANSCRIPT = ".system_generated/logs/transcript_full.jsonl"
_COMPACT_TRANSCRIPT = ".system_generated/logs/transcript.jsonl"
_USER_REQUEST = re.compile(r"<USER_REQUEST>\s*(.*?)\s*</USER_REQUEST>", re.DOTALL)
_HARNESS_BLOCKS = re.compile(
    r"<(?:ADDITIONAL_METADATA|USER_SETTINGS_CHANGE)>.*?</(?:ADDITIONAL_METADATA|USER_SETTINGS_CHANGE)>", re.DOTALL
)


class AntigravityImporter(BaseWireImporter):
    """Importer for local Antigravity conversation archives."""

    name: str = "Antigravity"
    id_key: str | None = "conversation_id"

    def import_(self, path: Path) -> list[EventLog]:
        transcripts: dict[str, tuple[str, str]] = {}
        conversations: dict[str, dict[str, Any]] = {}
        for entry in read_entries(path):
            if entry.get("endpoint") == "conversation" and (cid := entry.get("cid")):
                conversations[str(cid)] = json.loads(entry["response"])
                continue
            if entry.get("endpoint") != "file" or "path" not in entry:
                continue
            rel = PurePosixPath(entry["path"])
            if len(rel.parts) < 2:
                continue
            cid, inner = rel.parts[0], "/".join(rel.parts[1:])
            if inner == _FULL_TRANSCRIPT or (inner == _COMPACT_TRANSCRIPT and cid not in transcripts):
                transcripts[cid] = (entry["path"], entry_body(entry).decode("utf-8"))

        return [
            log
            for cid, (where, text) in transcripts.items()
            if (log := self._conversation(cid, text, where, conversations.get(cid))) is not None
        ]

    def _conversation(self, cid: str, transcript: str, where: str, info: dict[str, Any] | None) -> EventLog | None:
        """One conversation's transcript as a chat, or None if it is a subagent child or holds no turns."""
        meta_block = (info or {}).get("metadata") or {}
        if parent := meta_block.get("parentConversationId"):
            logger.info(f"Skipping {where}: subagent of {parent}")
            return None

        ordered: list[tuple[datetime, int, Message]] = []
        models: list[str | None] = []

        for index, data in enumerate(records(transcript, where)):
            if data.get("type") == "PLANNER_RESPONSE" and (model := data.get("model")):
                models.append(model)
            if message := _process_record(data):
                step = data.get("step_index")
                ordered.append((message.created, step if isinstance(step, int) else index, message))

        events = merged([msg for _, _, msg in sorted(ordered, key=lambda item: (item[0], item[1]))])
        if not events:
            logger.warning(f"No messages found in {where}")
            return None

        annotations = (info or {}).get("annotations") or {}
        state = (info or {}).get("state") or {}
        prompt = next((e.content.strip() for e in events if e.sender == Role.USER), "")
        first_line = shorten(prompt.splitlines()[0], 60, placeholder="…") if prompt else None
        title = (annotations.get("title") or "").strip() or (state.get("summary") or "").strip() or first_line or cid

        metadata: dict[str, Any] = {"conversation_id": cid}
        if project_id := meta_block.get("projectId"):
            metadata["project_id"] = project_id
        metadata |= models_field(models)

        return EventLog(created=events[0].created, events=events, title=title, metadata=metadata)


def _process_record(data: dict[str, Any]) -> Message | None:
    """One transcript line as a turn: user request, or agent prose and tool-call lines; outputs stay in the archive."""
    raw_created = data.get("created_at")
    if not raw_created:
        return None
    created = datetime.fromisoformat(raw_created)
    kind = data.get("type")

    if kind == "USER_INPUT":
        if data.get("source") != "USER_EXPLICIT":
            return None
        if text := _user_text(str(data.get("content") or "")):
            return Message(sender=Role.USER, content=text, created=created)
        return None

    if kind == "PLANNER_RESPONSE":
        parts: list[str] = []
        if content := str(data.get("content") or "").strip():
            parts.append(content)
        for call in data.get("tool_calls") or []:
            if isinstance(call, dict) and (name := call.get("name")):
                args = call.get("args")
                parts.append(tool_line(str(name), args if isinstance(args, dict) else {}))
        return Message(sender=Role.AGENT, content=joined(parts), created=created) if parts else None

    return None


def _user_text(content: str) -> str:
    """The prompt the user typed, stripped of the harness's `<USER_REQUEST>` and metadata wrappers."""
    if match := _USER_REQUEST.search(content):
        return match.group(1).strip()
    return _HARNESS_BLOCKS.sub("", content).strip()
