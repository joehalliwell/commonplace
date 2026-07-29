"""Tests for the ChatGPT importers (and, below, the fetcher)."""

import json
from pathlib import Path
from zipfile import ZipFile

from commonplace._import._chatgpt import ChatGptImporter


def _msg(node_id: str, role: str, text: str, **overrides) -> dict:
    message = {
        "id": node_id,
        "author": {"role": role, "name": None, "metadata": {}},
        "create_time": 1785132346.0,
        "content": {"content_type": "text", "parts": [text]},
        "recipient": "all",
        "metadata": {},
    }
    message.update(overrides)
    return message


def _conversation(mapping: dict, current_node: str | None = None, **overrides) -> dict:
    conversation = {
        "id": "conv-1",
        "title": "Test",
        "create_time": 1785132346.0,
        "mapping": mapping,
        "current_node": current_node,
    }
    conversation.update(overrides)
    return conversation


def _linear(*messages: dict) -> tuple[dict, str]:
    """Build a root + chain of message nodes. Returns (mapping, leaf_id)."""
    mapping: dict[str, dict] = {"root": {"id": "root", "message": None, "parent": None, "children": []}}
    prev = "root"
    for message in messages:
        node_id = message["id"]
        mapping[prev]["children"].append(node_id)
        mapping[node_id] = {"id": node_id, "message": message, "parent": prev, "children": []}
        prev = node_id
    return mapping, prev


def _zip(tmp_path: Path, conversations: list[dict]) -> Path:
    path = tmp_path / "chatgpt-export.zip"
    with ZipFile(path, "w") as zf:
        zf.writestr("conversations.json", json.dumps(conversations))
        zf.writestr("user.json", "{}")
    return path


def _import(tmp_path: Path, conversation: dict):
    return ChatGptImporter().import_(_zip(tmp_path, [conversation]))[0]


def test_import_reads_a_linear_thread(tmp_path):
    mapping, leaf = _linear(_msg("a", "user", "hello"), _msg("b", "assistant", "hi back"))
    log = _import(tmp_path, _conversation(mapping, current_node=leaf))

    assert [e.content for e in log.events] == ["hello", "hi back"]


def test_import_follows_the_branch_ending_at_current_node(tmp_path):
    """A regenerate forks the mapping. `children[0]` is the abandoned branch;
    `current_node` names the leaf of the live one."""
    mapping, _ = _linear(_msg("a", "user", "hello"))
    for node_id, text in (("abandoned", "first attempt"), ("kept", "second attempt")):
        mapping["a"]["children"].append(node_id)
        mapping[node_id] = {
            "id": node_id,
            "message": _msg(node_id, "assistant", text),
            "parent": "a",
            "children": [],
        }

    log = _import(tmp_path, _conversation(mapping, current_node="kept"))

    assert [e.content for e in log.events] == ["hello", "second attempt"]


def test_import_falls_back_to_first_child_without_current_node(tmp_path):
    mapping, _ = _linear(_msg("a", "user", "hello"), _msg("b", "assistant", "hi back"))
    log = _import(tmp_path, _conversation(mapping, current_node=None))

    assert [e.content for e in log.events] == ["hello", "hi back"]


def test_import_skips_tool_traffic(tmp_path):
    """`recipient` other than "all" addresses a tool, not the conversation."""
    mapping, leaf = _linear(
        _msg("a", "user", "search for badgers"),
        _msg("b", "assistant", '{"query": "badgers"}', recipient="web"),
        _msg("c", "assistant", "Badgers are mustelids."),
    )
    log = _import(tmp_path, _conversation(mapping, current_node=leaf))

    assert [e.content for e in log.events] == ["search for badgers", "Badgers are mustelids."]


def test_import_skips_visually_hidden_messages(tmp_path):
    """The flag lives on the message's metadata, not the node's."""
    mapping, leaf = _linear(
        _msg("a", "user", "context injected by the client", metadata={"is_visually_hidden_from_conversation": True}),
        _msg("b", "user", "hello"),
        _msg("c", "assistant", "hi back"),
    )
    log = _import(tmp_path, _conversation(mapping, current_node=leaf))

    assert [e.content for e in log.events] == ["hello", "hi back"]


def test_import_skips_non_text_content(tmp_path):
    """`code` blocks carry `text`/`language` and no `parts`."""
    mapping, leaf = _linear(
        _msg("a", "user", "hello"),
        _msg(
            "b",
            "assistant",
            "",
            content={"content_type": "code", "language": "unknown", "text": "search(...)"},
            recipient="all",
        ),
        _msg("c", "assistant", "hi back"),
    )
    log = _import(tmp_path, _conversation(mapping, current_node=leaf))

    assert [e.content for e in log.events] == ["hello", "hi back"]


def test_import_uses_conversation_id_when_id_absent(tmp_path):
    """Fetched detail responses carry `conversation_id`; exports carry `id`."""
    mapping, leaf = _linear(_msg("a", "user", "hello"))
    conversation = _conversation(mapping, current_node=leaf)
    del conversation["id"]
    conversation["conversation_id"] = "from-wire"

    log = _import(tmp_path, conversation)

    assert log.metadata["id"] == "from-wire"
