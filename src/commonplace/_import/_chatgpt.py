"""Importers for ChatGPT conversations, from either the export ZIP or the
`chatgpt-wire.jsonl.gz` archive produced by [[ChatGptFetcher]].

Both sources carry the same `mapping` tree, so the parse below is shared. They
differ only in keying the conversation `id` vs `conversation_id`, and in dating
it with an ISO string vs an epoch float.
"""

import json
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zipfile import ZipFile

from commonplace._import._types import EventLog, Message, Role
from commonplace._logging import logger
from commonplace._wire import read_entries, read_header

DEFAULT_TIME = datetime.fromtimestamp(0, tz=UTC)  # Default time if not provided

SOURCE = "chatgpt"


class ChatGptWireImporter:
    """Consumes the fetcher's wire archive. Born at wire version 2, so there is
    no headerless archive to recognise."""

    source: str = SOURCE

    def required_paths(self) -> list[str]:
        return []

    def can_import(self, path: Path) -> bool:
        return read_header(path)[0] == self.source

    def import_(self, path: Path) -> list[EventLog]:
        return [
            _to_log(json.loads(entry["response"]))
            for entry in read_entries(path)
            if entry["endpoint"] == "conversation"
        ]


class ChatGptImporter:
    """Consumes the ChatGPT export ZIP."""

    source: str = SOURCE

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

        return [_to_log(conversation) for conversation in conversations]


def _to_log(conversation: dict[str, Any]) -> EventLog:
    """Convert a conversation dictionary to an EventLog."""
    # Export ZIPs key it `id`; fetched detail responses use `conversation_id`.
    metadata = {"id": conversation.get("id") or conversation["conversation_id"]}

    return EventLog(
        source=SOURCE,
        created=_timestamp(conversation.get("create_time")),
        events=list(_messages(conversation)),
        title=conversation["title"],
        metadata=metadata,
    )


def _messages(conversation: dict[str, Any]):
    """Yield the messages of the conversation's live branch."""
    nodes = conversation["mapping"]
    for node_id in _thread(nodes, conversation.get("current_node")):
        msg = _to_message(nodes[node_id])
        if msg:
            yield msg


def _thread(nodes: dict[str, Any], current_node: str | None) -> list[str]:
    """Node ids from root to leaf along the live branch.

    `mapping` is a tree, not a chain: editing a prompt or regenerating a reply
    forks it. `current_node` is the leaf ChatGPT itself considers current, so
    walk up from there via `parent`. Descending through `children[0]` instead
    picks the *abandoned* fork and truncates the conversation at the first
    regenerate.
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


def _to_message(node: dict[str, Any]) -> Message | None:
    msg = node.get("message")
    if not msg or "content" not in msg:
        return None

    id_ = msg["id"]

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

    content = msg["content"]
    content_type = content["content_type"]

    # `code`, `execution_output` and friends carry `text`, not `parts`.
    if content_type not in ("text", "multimodal_text"):
        logger.info(f"Skipping {content_type} message {id_}")
        return None

    text = "\n".join(_part(part) for part in content["parts"])
    if not text:
        logger.info(f"Skipping empty message {id_}")
        return None

    return Message(
        sender=Role.USER if msg["author"]["role"] == "user" else Role.ASSISTANT,
        content=text,
        created=_timestamp(msg.get("create_time")),
    )


def _part(part: Any) -> str:
    if isinstance(part, str):
        return part

    json_ = json.dumps(part, indent=2)
    return f"```json\n{json_}\n```"


def _timestamp(ts: float | None) -> datetime:
    if ts is None:
        return DEFAULT_TIME
    return datetime.fromtimestamp(ts, tz=UTC)
