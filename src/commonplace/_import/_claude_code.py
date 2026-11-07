import json
import re
from collections.abc import Iterator
from pathlib import Path
from textwrap import shorten
from typing import Any

from commonplace._import._base import BaseWireImporter
from commonplace._import._types import Event, EventLog, Message, Role, ToolCall, models_field
from commonplace._logging import logger
from commonplace._utils import truncate
from commonplace._wire import read_entries


class ClaudeCodeImporter(BaseWireImporter):
    """Importer for the `claude-code-wire.jsonl.gz` archive [[ClaudeCodeFetcher]] records.

    Each entry is `{"endpoint": "session", "path": ..., "response": ...}`, whose `response` is a session's
    transcript verbatim: JSONL in the Anthropic Messages API format.
    """

    source: str = "claude-code"
    name: str = "Claude Code"
    id_key: str | None = "sessionId"

    def import_(self, path: Path) -> list[EventLog]:
        return [log for entry in read_entries(path) for log in self._session(entry["response"], entry["path"])]

    def _session(self, transcript: str, where: str) -> list[EventLog]:
        """One session's transcript as a chat, or none if it holds no turns."""
        events: list[Event] = []
        required_metadata = (
            "sessionId",
            "timestamp",
            "cwd",
            "summary",
        )
        metadata = {}
        models: list[str | None] = []
        tool_calls: dict[str, ToolCall] = {}
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

            if message := self._process_event(data, tool_calls):
                events.append(message)

        # Add in the tool calls and sort
        events.extend(tool_calls.values())
        events.sort(key=lambda evt: evt.created)

        if not events:
            logger.warning(f"No messages found in {where}")
            return []

        # Ensure metadata is correctly ordered for the frontmatter
        metadata = {k: metadata[k] for k in required_metadata if k in metadata} | models_field(models)

        # Extract title and created time
        created = metadata.pop("timestamp")
        summary = metadata.pop("summary", None)
        prompt = next((e.content.strip() for e in events if isinstance(e, Message) and e.sender == Role.USER), "")
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
    def _process_event(data: dict[str, Any], tool_calls: dict[str, ToolCall]) -> Message | None:
        """Parse a user or assistant message from Messages API format."""
        msg_type = data["type"]

        # A prompt typed while the agent works is absorbed mid-turn and recorded only as an attachment.
        attachment = data.get("attachment") or {}
        if attachment.get("type") == "queued_command" and (attachment.get("origin") or {}).get("kind") == "human":
            return Message(sender=Role.USER, content=attachment["prompt"], created=data["timestamp"])

        if msg_type not in {"user", "assistant"}:
            logger.debug(f"Skipping unhandled message type {msg_type}")
            return None

        # Determine role from message type
        role = Role.USER if msg_type == "user" else Role.AGENT

        # Extract content from message structure
        content = data["message"]["content"]

        if not content:
            logger.warning(f"Skipping message without content: {truncate(str(data))}")
            return None

        # Handle basic (single-part) content as string
        if isinstance(content, str):
            if role == Role.USER:
                role, content = _attribute(data, content)
            return Message(sender=role, content=content, created=data["timestamp"])

        # Handle multi-part content
        assert isinstance(content, list)

        # Parse content blocks (array format)
        blocks = []
        for block in content:
            block_type = block["type"]

            if block_type == "text":
                blocks.append(block["text"])

            elif block_type == "thinking":
                # Include thinking blocks as collapsed sections; a redacted one carries only its signature
                if thinking := block["thinking"]:
                    blocks.append(f"<!--\n{thinking}\n-->")

            elif block_type == "tool_use":
                # Format tool calls
                tool_use_id = block["id"]
                tool_name = block["name"]
                tool_input = block.get("input", {})
                timestamp = data["timestamp"]

                tool_calls[tool_use_id] = ToolCall(created=timestamp, tool=tool_name, args=tool_input, output="PENDING")

            elif block_type == "tool_result":
                output = block["content"]
                # An image's base64 would swamp the note; the stored session keeps it.
                if isinstance(output, list):
                    output = [{"type": "image"} if part.get("type") == "image" else part for part in output]
                tool_calls[block["tool_use_id"]].output = output

            else:
                logger.debug(f"Skipping {block_type} content block")
                blocks.append(f"<!-- Skipped content of type {block_type} -->")

        # If there's no direct output i.e. we're just dealing with tool results
        if not blocks:
            return None

        content = "\n\n".join(blocks)
        if role == Role.USER:
            role, content = _attribute(data, content)

        return Message(sender=role, content=content, created=data["timestamp"])


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
