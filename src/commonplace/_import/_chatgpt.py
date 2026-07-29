import json
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zipfile import ZipFile

from commonplace._import._types import EventLog, Message, Role
from commonplace._logging import logger

DEFAULT_TIME = datetime.fromtimestamp(0, tz=UTC)  # Default time if not provided


class ChatGptImporter:
    """Importer for ChatGPT notes."""

    source: str = "chatgpt"

    def required_paths(self) -> list[str]:
        return ["conversations.json", "user.json"]

    def can_import(self, path: Path) -> bool:
        """Check if the importer can handle the given file path."""
        with closing(ZipFile(path, "r")) as zf:
            files = zf.namelist()
            assert "conversations.json" in files
            assert "user.json" in files
            return True

    def import_(self, path: Path) -> list[EventLog]:
        """Import activity logs from the ChatGPT file."""
        with closing(ZipFile(path)) as zf:
            conversations = json.loads(zf.read("conversations.json"))

        return [self._to_log(conversation) for conversation in conversations]

    def _to_log(self, conversation: dict[str, Any]) -> EventLog:
        """Convert a conversation dictionary to an ActivityLog object."""
        # Export ZIPs key it `id`; fetched detail responses use `conversation_id`.
        metadata = {"id": conversation.get("id") or conversation["conversation_id"]}
        title = conversation["title"]
        created = self._timestamp(conversation.get("create_time"))
        messages = list(self._messages(conversation))

        return EventLog(
            source=self.source,
            created=created,
            events=messages,
            title=title,
            metadata=metadata,
        )

    def _messages(self, conversation: dict[str, Any]):
        """Yield the messages of the conversation's live branch."""
        nodes = conversation["mapping"]
        for node_id in self._thread(nodes, conversation.get("current_node")):
            msg = self._to_message(nodes[node_id])
            if msg:
                yield msg

    def _thread(self, nodes: dict[str, Any], current_node: str | None) -> list[str]:
        """Node ids from root to leaf along the live branch.

        `mapping` is a tree, not a chain: editing a prompt or regenerating a
        reply forks it. `current_node` is the leaf ChatGPT itself considers
        current, so walk up from there via `parent`. Descending through
        `children[0]` instead picks the *abandoned* fork and truncates the
        conversation at the first regenerate.
        """
        if current_node is not None:
            thread = []
            node_id: str | None = current_node
            while node_id is not None:
                thread.append(node_id)
                node_id = nodes[node_id]["parent"]
            return list(reversed(thread))

        # No current_node (older exports): descend, warning at each fork.
        root = next((id_ for id_, node in nodes.items() if node["parent"] is None), None)
        assert root is not None, "No root node found in conversation mapping"
        thread = [root]
        while children := nodes[thread[-1]]["children"]:
            if len(children) > 1:
                logger.warning(f"No current_node and {thread[-1]} forks; following the first child")
            thread.append(children[0])
        return thread

    def _to_message(self, node: dict[str, Any]) -> Message | None:
        msg = node.get("message")
        if not msg or "content" not in msg:
            return None

        id_ = msg["id"]
        created = self._timestamp(msg.get("create_time"))

        # Client-injected context (custom instructions, memory) is carried as a
        # real message but never shown; it isn't part of the conversation.
        if msg.get("metadata", {}).get("is_visually_hidden_from_conversation", False):
            logger.debug(f"Skipping message hidden from the conversation {id_}")
            return None

        # `recipient` addresses a tool ("web", "python", ...) rather than the
        # conversation. Tool calls and their results are working, not record.
        recipient = msg.get("recipient", "all")
        if recipient != "all":
            logger.debug(f"Skipping message {id_} addressed to {recipient}")
            return None

        role = msg["author"]["role"]
        content = msg["content"]
        content_type = content["content_type"]

        # `code`, `execution_output` and friends carry `text`, not `parts`.
        if content_type not in ("text", "multimodal_text"):
            logger.info(f"Skipping {content_type} message {id_}")
            return None

        parts = content["parts"]
        content = "\n".join(self._part(part) for part in parts)
        if not content:
            logger.info(f"Skipping empty message {id_}")
            return None

        return Message(
            sender=Role.USER if role == "user" else Role.ASSISTANT,
            content=content,
            created=created,
            # metadata={"id": id_},
        )

    def _part(self, part: Any) -> str:
        if isinstance(part, str):
            return part

        json_ = json.dumps(part, indent=2)
        return f"```json\n{json_}\n```"

    def _timestamp(self, ts: float | None) -> datetime:
        if ts is None:
            return DEFAULT_TIME
        return datetime.fromtimestamp(ts, tz=UTC)
