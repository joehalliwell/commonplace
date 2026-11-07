import json
from pathlib import Path
from typing import Any

from commonplace._import._types import Event, EventLog, Message, Role, ToolCall, models_field
from commonplace._logging import logger
from commonplace._utils import truncate


class ClaudeCodeImporter:
    """
    Importer for Claude Code conversation logs.

    Handles JSONL files from ~/.claude/projects/ which use the
    Anthropic Messages API format.
    """

    source: str = "claude-code"
    name: str = "Claude Code"
    member: str | None = None  # Not an archive
    id_key: str | None = "sessionId"

    def can_import(self, path: Path) -> bool:
        """Check if this is a Claude Code JSONL file."""
        if path.suffix != ".jsonl":
            return False

        # The preamble of harness lines before the first turn grows with each release, so read until it.
        with open(path, "r") as fp:
            for line in fp:
                data = json.loads(line)
                if data["type"] == "user":
                    return "sessionId" in data
        return False

    def import_(self, path: Path) -> list[EventLog]:
        """Import a single Claude Code conversation from JSONL file."""
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

        for line in path.read_text(encoding="utf-8").splitlines():
            data = json.loads(line)

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
            logger.warning(f"No messages found in {path}")
            return []

        # Ensure metadata is correctly ordered for the frontmatter
        metadata = {k: metadata[k] for k in required_metadata if k in metadata} | models_field(models)

        # Extract title and created time
        created = metadata.pop("timestamp")
        summary = metadata.pop("summary", metadata["sessionId"])
        title = ai_title or summary

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

        if msg_type not in {"user", "assistant"}:
            logger.warning(f"Skipping unhandled message type {msg_type}")
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
            timestamp = data["timestamp"]
            return Message(sender=role, content=content, created=timestamp)

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
                # Format tool results
                content = block["content"]
                tool_use_id = block["tool_use_id"]
                output = block["content"]
                call = tool_calls[tool_use_id]
                call.output = output

            else:
                logger.debug(f"Skipping {block_type} content block")
                blocks.append(f"<!-- Skipped content of type {block_type} -->")

        # If there's no direct output i.e. we're just dealing with tool results
        if not blocks:
            return None

        content = "\n\n".join(blocks)
        timestamp = data["timestamp"]

        return Message(
            sender=role,
            content=content,
            created=timestamp,
        )
