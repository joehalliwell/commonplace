import json
import re
from collections.abc import Iterator
from pathlib import Path, PurePosixPath
from textwrap import shorten
from typing import Any

from commonplace._import._base import BaseWireImporter
from commonplace._import._types import EventLog, Message, Role, models_field
from commonplace._logging import logger
from commonplace._utils import truncate
from commonplace._wire import entry_body, read_entries


class ClaudeCodeImporter(BaseWireImporter):
    """Importer for the `claude-code-wire.jsonl.xz` archive [[ClaudeCodeFetcher]] records.

    Each entry is `{"endpoint": "session", "path": ..., "response": ...}`, whose `response` is a session's
    transcript verbatim: JSONL in the Anthropic Messages API format.
    """

    source: str = "claude-code"
    name: str = "Claude Code"
    id_key: str | None = "sessionId"

    def import_(self, path: Path) -> list[EventLog]:
        transcripts = (e for e in read_entries(path) if _is_transcript(e["path"]))
        return [log for e in transcripts for log in self._session(entry_body(e).decode("utf-8"), e["path"])]

    def _session(self, transcript: str, where: str) -> list[EventLog]:
        """One session's transcript as a chat, or none if it holds no turns."""
        events: list[Message] = []
        required_metadata = (
            "sessionId",
            "timestamp",
            "cwd",
            "summary",
        )
        metadata = {}
        models: list[str | None] = []
        ai_title: str | None = None

        for data in _records(transcript, where):
            # Claude Code refines its title as the session goes, so the last one wins.
            if data.get("type") == "ai-title":
                ai_title = data["aiTitle"]

            # `<synthetic>` marks a message the harness wrote, not a model.
            if data.get("type") == "assistant" and (model := data["message"].get("model")) != "<synthetic>":
                models.append(model)

            # Extract session metadata opportunistically from envelope or message
            for required in required_metadata:
                if required in metadata:
                    continue
                if val := data.get(required, data.get("message", {}).get(required)):
                    metadata[required] = val

            if message := self._process_event(data):
                events.append(message)

        events = _merged(sorted(events, key=lambda evt: evt.created))

        if not events:
            logger.warning(f"No messages found in {where}")
            return []

        # Ensure metadata is correctly ordered for the frontmatter
        metadata = {k: metadata[k] for k in required_metadata if k in metadata} | models_field(models)

        # Extract title and created time
        created = metadata.pop("timestamp")
        summary = metadata.pop("summary", None)
        prompt = next((e.content.strip() for e in events if e.sender == Role.USER), "")
        first_line = shorten(prompt.splitlines()[0], 60, placeholder="…") if prompt else None
        title = ai_title or summary or first_line or metadata["sessionId"]

        return [
            EventLog(
                source=self.source,
                created=created,
                events=events,
                title=title,
                metadata=metadata,
            )
        ]

    @staticmethod
    def _process_event(data: dict[str, Any], tools: bool = True) -> Message | None:
        """A record as a turn: what the user or agent said, each tool call a line; its output stays in the archive."""
        msg_type = data["type"]

        # A prompt typed while the agent works is absorbed mid-turn and recorded only as an attachment.
        attachment = data.get("attachment") or {}
        if attachment.get("type") == "queued_command" and (attachment.get("origin") or {}).get("kind") == "human":
            return Message(sender=Role.USER, content=attachment["prompt"], created=data["timestamp"])

        if msg_type not in {"user", "assistant"}:
            logger.debug(f"Skipping unhandled message type {msg_type}")
            return None

        if answers := _answers(data):
            return Message(sender=Role.USER, content=answers, created=data["timestamp"])

        role = Role.USER if msg_type == "user" else Role.AGENT
        content = data["message"]["content"]

        if not content:
            logger.warning(f"Skipping message without content: {truncate(str(data))}")
            return None

        if isinstance(content, list):
            blocks = []
            for block in content:
                block_type = block["type"]
                if block_type == "text":
                    blocks.append(block["text"])
                elif block_type == "tool_use":
                    if tools:
                        blocks.append(_tool_line(block["name"], block.get("input", {})))
                elif block_type not in {"thinking", "redacted_thinking", "tool_result"}:
                    logger.debug(f"Skipping {block_type} content block")
                    blocks.append(f"<!-- Skipped content of type {block_type} -->")
            if not blocks:
                return None
            content = _joined(blocks)

        if role == Role.USER:
            role, content = _attribute(data, content)
        if role == Role.SYSTEM:
            return None
        return Message(sender=role, content=content, created=data["timestamp"])


def _tool_line(name: str, tool_input: dict[str, Any]) -> str:
    """A tool call as a list item: its name and first text argument, on one shortened line."""
    target = next((" ".join(v.split()) for v in tool_input.values() if isinstance(v, str) and v.strip()), None)
    if target is None:
        return f"- {name}"
    if len(target) > _TOOL_LINE:
        target = target[: _TOOL_LINE - 1] + "…"
    ticks = "`" * (max((len(run) for run in re.findall(r"`+", target)), default=0) + 1)
    pad = " " if target.startswith("`") or target.endswith("`") else ""
    return f"- {name}: {ticks}{pad}{target}{pad}{ticks}"


_TOOL_LINE = 80


def _joined(parts: list[str]) -> str:
    """Parts as paragraphs, but adjacent list items as one list."""
    joined = parts[0]
    for part in parts[1:]:
        tight = joined.rsplit("\n", 1)[-1].startswith("- ") and part.startswith("- ")
        joined += ("\n" if tight else "\n\n") + part
    return joined


def _merged(events: list[Message]) -> list[Message]:
    """Consecutive agent records as one turn, as it was had: Claude Code writes each content block as a record."""
    merged: list[Message] = []
    for event in events:
        if merged and event.sender == merged[-1].sender == Role.AGENT:
            merged[-1] = merged[-1].model_copy(update={"content": _joined([merged[-1].content, event.content])})
        else:
            merged.append(event)
    return merged


def _answers(data: dict[str, Any]) -> str | None:
    """The user's answers to the agent's questions: a tool result, but the user's words."""
    result = data.get("toolUseResult")
    if not (isinstance(result, dict) and isinstance(answers := result.get("answers"), dict)):
        return None
    annotations = result.get("annotations") or {}

    def answer(question: str, choice: str) -> str:
        quoted = "\n".join(f"> {line}" for line in question.splitlines())
        notes = (annotations.get(question) or {}).get("notes")
        return f"{quoted}\n\n{choice}" + (f": {notes}" if notes else "")

    return "\n\n".join(answer(q, a) for q, a in answers.items())


def _is_transcript(path: str) -> bool:
    """A session's own transcript, `<project>/<session>.jsonl`: a note is the session as it was had, so not its
    subagents or tool results, nor an orphaned copy, which repeats its session's id."""
    parts = PurePosixPath(path).parts
    return len(parts) == 2 and parts[1].endswith(".jsonl") and ".orphaned-" not in parts[1]


def _records(transcript: str, where: str) -> Iterator[dict[str, Any]]:
    """The transcript's lines, parsed; a session fetched while running can end mid-line, and the next fetch has it."""
    lines = [line for line in transcript.splitlines() if line.strip()]
    for i, line in enumerate(lines):
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            if i < len(lines) - 1:
                raise
            logger.warning(f"Dropping the half-written last line of {where}")


_HARNESS_TAGS = (
    "<local-command-stdout>",
    "<local-command-stderr>",
    "<local-command-caveat>",
    "<bash-stdout>",
    "<bash-stderr>",
    "<task-notification>",
    "<system-reminder>",
)


def _attribute(data: dict[str, Any], content: str) -> tuple[Role, str]:
    """Who wrote a user-role turn: the user, as typed or as the command they ran, or the harness."""
    text = content.lstrip()
    if data.get("isMeta") or data.get("isCompactSummary") or text.startswith(_HARNESS_TAGS):
        return Role.SYSTEM, content
    if text.startswith("<command-") and (name := re.search(r"<command-name>(.*?)</command-name>", text)):
        args = re.search(r"<command-args>(.*?)</command-args>", text, re.DOTALL)
        return Role.USER, " ".join(filter(None, [name[1], args and args[1].strip()]))
    if bash := re.fullmatch(r"<bash-input>(.*?)</bash-input>\s*", text, re.DOTALL):
        return Role.USER, f"!{bash[1]}"
    return Role.USER, content
