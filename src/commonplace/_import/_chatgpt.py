import json
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from zipfile import ZipFile

from commonplace._import._types import ActivityLog, Importer, Message, Role
from commonplace._utils import logger

DEFAULT_TIME = datetime.fromtimestamp(0, tz=timezone.utc)  # Default time if not provided


class ChatGptImporter(Importer):
    """Importer for ChatGPT notes."""

    source: str = "chatgpt"

    def can_import(self, path: Path) -> bool:
        """Check if the importer can handle the given file path."""
        try:
            with closing(ZipFile(path, "r")) as zf:
                files = zf.namelist()
                assert "conversations.json" in files
                assert "user.json" in files
                return True

        except Exception as e:
            logger.info(
                f"{path} failed {self} importability check: {e}",
                exc_info=True,
            )
            return False

    def import_(self, path: Path) -> list[ActivityLog]:
        """Import activity logs from the ChatGPT file."""
        with closing(ZipFile(path)) as zf:
            conversations = json.loads(zf.read("conversations.json"))

        return [self._to_log(conversation) for conversation in conversations]

    def _to_log(self, conversation: dict[str, Any]) -> ActivityLog:
        """Convert a conversation dictionary to an ActivityLog object."""
        metadata = {"id": conversation["id"]}
        title = conversation["title"]
        created = self._timestamp(conversation.get("create_time"))
        messages = list(self._messages(conversation))

        return ActivityLog(
            source=self.source,
            created=created,
            messages=messages,
            title=title,
            metadata=metadata,
        )

    def _messages(self, conversation: dict[str, Any]):
        """Extract thread IDs from a conversation."""
        nodes = conversation["mapping"]
        current_id = None
        # Find the root node (the one without a parent)
        for id_, node in conversation["mapping"].items():
            if node["parent"] is None:
                current_id = id_
                break
        assert current_id is not None, "No root node found in conversation mapping"

        # Now walk the thread
        while True:
            current_node = nodes[current_id]
            msg = self._to_message(current_node)
            if msg:
                yield msg

            # Follow thread
            children = current_node["children"]
            if len(children) == 0:
                break
            # Get the first child node
            if len(children) > 1:
                logger.warning(f"Multiple children found for node {current_id}, using the first one")
            current_id = children[0]

    def _to_message(self, node: dict[str, Any]) -> Optional[Message]:
        msg = node.get("message")
        if not msg or "content" not in msg:
            return None
        # if node.get("metadata", {}).get("is_visually_hidden_from_conversation", False):
        #     return None

        id_ = msg["id"]
        created = self._timestamp(msg.get("create_time"))

        role = msg["author"]["role"]
        content = msg["content"]
        content_type = content["content_type"]

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

    def _timestamp(self, ts: Optional[float]) -> datetime:
        if ts is None:
            return DEFAULT_TIME
        return datetime.fromtimestamp(ts, tz=timezone.utc)
