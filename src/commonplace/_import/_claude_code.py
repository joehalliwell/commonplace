import json
from itertools import islice
from pathlib import Path
from typing import Any

from commonplace._import._types import Event, EventLog, Importer, Message, Role, ToolCall
from commonplace._logging import logger
from commonplace._utils import truncate


class ClaudeCodeImporter(Importer):
    """
    Importer for Claude Code conversation logs.

    Handles JSONL files from ~/.claude/projects/ which use the
    Anthropic Messages API format.
    """

    source: str = "claude-code"

    def can_import(self, path: Path) -> bool:
        """Check if this is a Claude Code JSONL file."""
        if path.suffix != ".jsonl":
            return False

        messages_by_type: dict[str, dict] = {}

        with open(path, "r") as fp:
            for line in islice(fp, 5):
                data = json.loads(line)
                messages_by_type[data["type"]] = data

        # Not always present...
        # assert "file-history-snapshot" in messages_by_type
        assert "user" in messages_by_type
        assert "sessionId" in messages_by_type["user"]

        return True

    def import_(self, path: Path) -> list[EventLog]:
        """Import a single Claude Code conversation from JSONL file."""
        events: list[Event] = []
        required_metadata = (
            "sessionId",
            "timestamp",
            "cwd",
            "summary",
            "model",
        )
        metadata = dict()
        tool_calls: dict[str, ToolCall] = {}

        for line in open(path, "r"):
            data = json.loads(line)

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
        metadata = {k: metadata[k] for k in required_metadata if k in metadata}

        # Extract title and created time
        created = metadata.pop("timestamp")
        title = metadata.pop("summary", metadata["sessionId"])

        return [
            EventLog(
                source=self.source,
                created=created,
                events=events,
                title=title,
                metadata=metadata,
            )
        ]

    def _process_event(self, data: dict[str, Any], tool_calls: dict[str, ToolCall]) -> Message | None:
        """Parse a user or assistant message from Messages API format."""
        msg_type = data["type"]

        if msg_type not in {"user", "assistant"}:
            logger.warning(f"Skipping unhandled message type {msg_type}")
            return None

        # Determine role from message type
        role = Role.USER if msg_type == "user" else Role.ASSISTANT

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
                # Include thinking blocks as collapsed sections
                thinking = block["thinking"]
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
