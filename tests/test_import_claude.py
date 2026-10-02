"""Tests for the Claude importers: ClaudeImporter (fetcher wire) and ClaudeExportImporter (ZIP)."""

import json
import logging
from zipfile import ZipFile

from commonplace._import._claude import ClaudeImporter
from commonplace._import._claude_export import ClaudeExportImporter
from commonplace._wire import write_archive


def test_wire_importer_accepts_fetcher_output(tmp_path, write_jsonl_gz):
    path = write_jsonl_gz(tmp_path / "claude-wire.jsonl.gz", [{"endpoint": "conversations", "response": []}])
    assert ClaudeImporter().can_import(path)


def test_wire_importer_rejects_arbitrary_jsonl_gz(tmp_path, write_jsonl_gz):
    path = write_jsonl_gz(tmp_path / "other.jsonl.gz", [{"not": "ours"}])
    assert not ClaudeImporter().can_import(path)


_THREAD = {
    "uuid": "abc",
    "name": "Hi",
    "created_at": "2026-07-15T00:00:00Z",
    "chat_messages": [
        {"sender": "human", "text": "hello", "created_at": "2026-07-15T00:00:00Z"},
        {"sender": "assistant", "text": "hi back", "created_at": "2026-07-15T00:00:01Z"},
    ],
}


def _entries(response) -> list[dict]:
    return [
        {"endpoint": "conversations", "response": "[]"},
        {"endpoint": "conversation", "cid": "abc", "response": response},
    ]


def test_wire_importer_wraps_flat_text(tmp_path):
    """Fetcher-wire messages have only `text`; the importer wraps into blocks."""
    path = write_archive(tmp_path / "claude-wire.jsonl.gz", "claude", _entries(json.dumps(_THREAD)))

    logs = ClaudeImporter().import_(path)
    assert len(logs) == 1
    assert [e.content for e in logs[0].events] == ["hello", "hi back"]


def test_wire_importer_reads_legacy_parsed_responses(tmp_path, write_jsonl_gz):
    """v1 archives have no header and hold `response` already parsed. They are
    committed in users' repos, so they must still import."""
    path = write_jsonl_gz(tmp_path / "claude-wire.jsonl.gz", _entries(_THREAD))

    logs = ClaudeImporter().import_(path)
    assert len(logs) == 1
    assert [e.content for e in logs[0].events] == ["hello", "hi back"]


def _thread_with_message(message: dict) -> dict:
    return {**_THREAD, "chat_messages": [message]}


def test_wire_importer_flags_a_message_with_no_text_at_all(tmp_path, caplog):
    """The silent-corruption path. If Anthropic renames `text`, a message with
    neither `content` nor `text` used to import as an empty string — no error,
    straight into git. Say so in the log and in the note instead."""
    message = {"sender": "human", "created_at": "2026-07-15T00:00:00Z", "prose": "renamed!"}
    path = write_archive(
        tmp_path / "claude-wire.jsonl.gz", "claude", _entries(json.dumps(_thread_with_message(message)))
    )

    with caplog.at_level(logging.WARNING, logger="commonplace"):
        logs = ClaudeImporter().import_(path)

    assert "no recoverable text" in logs[0].events[0].content
    assert any("no content or text" in r.message for r in caplog.records)


def test_wire_importer_keeps_a_deliberately_empty_message_empty(tmp_path, caplog):
    """`text: ""` is a message that really is empty — attachments only, say.
    Flagging it would cry wolf on every one of them."""
    message = {"sender": "human", "created_at": "2026-07-15T00:00:00Z", "text": ""}
    path = write_archive(
        tmp_path / "claude-wire.jsonl.gz", "claude", _entries(json.dumps(_thread_with_message(message)))
    )

    with caplog.at_level(logging.WARNING, logger="commonplace"):
        logs = ClaudeImporter().import_(path)

    assert logs[0].events[0].content == ""
    assert not [r for r in caplog.records if "no content or text" in r.message]


def test_export_importer_requires_users_json(tmp_path):
    """A ZIP with only conversations.json (like ChatGPT's export) is rejected."""
    path = tmp_path / "not-claude.zip"
    with ZipFile(path, "w") as zf:
        zf.writestr("conversations.json", "[]")
    assert not ClaudeExportImporter().can_import(path)


def test_export_importer_accepts_full_pair(tmp_path):
    path = tmp_path / "claude-export.zip"
    with ZipFile(path, "w") as zf:
        zf.writestr("conversations.json", "[]")
        zf.writestr("users.json", "[]")
    assert ClaudeExportImporter().can_import(path)


def test_export_importer_preserves_content_blocks(tmp_path):
    """Export-ZIP messages carry populated content blocks — importer uses
    them directly rather than falling back to flat `text`."""
    thread = {
        "uuid": "abc",
        "name": "Hi",
        "created_at": "2026-07-15T00:00:00Z",
        "chat_messages": [
            {
                "sender": "human",
                "text": "ignored",  # export has both; importer prefers content
                "created_at": "2026-07-15T00:00:00Z",
                "content": [{"type": "text", "text": "real user text"}],
            },
        ],
    }
    path = tmp_path / "claude-export.zip"
    with ZipFile(path, "w") as zf:
        zf.writestr("conversations.json", json.dumps([thread]))
        zf.writestr("users.json", "[]")

    logs = ClaudeExportImporter().import_(path)
    assert logs[0].events[0].content == "real user text"
