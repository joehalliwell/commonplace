"""Tests for the Claude importers: ClaudeImporter (fetcher wire) and ClaudeExportImporter (ZIP)."""

import json
import logging
from zipfile import ZipFile

from commonplace._import._claude import ClaudeImporter
from commonplace._import._claude_export import ClaudeExportImporter
from commonplace._import._types import Role
from commonplace._wire import write_archive
from tests.fetching import owned


def test_wire_importer_accepts_fetcher_output(tmp_path, write_jsonl_gz):
    path = write_jsonl_gz(tmp_path / "claude-wire.jsonl.gz", [{"endpoint": "conversations", "response": []}])
    assert owned(ClaudeImporter).can_import(path)


def test_wire_importer_rejects_arbitrary_jsonl_gz(tmp_path, write_jsonl_gz):
    path = write_jsonl_gz(tmp_path / "other.jsonl.gz", [{"not": "ours"}])
    assert not owned(ClaudeImporter).can_import(path)


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

    logs = owned(ClaudeImporter).import_(path)
    assert len(logs) == 1
    assert [e.content for e in logs[0].events] == ["hello", "hi back"]


def test_wire_importer_renders_each_tool_call_as_a_line(tmp_path):
    """As a Claude Code note does: what the tool returned, and the thinking, stay in the archive."""
    reply = [
        {"type": "thinking", "thinking": "Hmm."},
        {"type": "tool_use", "name": "web_search", "input": {"query": "news"}},
        {"type": "tool_result", "name": "web_search", "content": [{"type": "text", "text": "x"}]},
        {"type": "text", "text": "Nothing new."},
    ]
    thread = _THREAD | {"chat_messages": [_THREAD["chat_messages"][1] | {"text": "", "content": reply}]}
    path = write_archive(tmp_path / "claude-wire.jsonl.gz", "claude", _entries(json.dumps(thread)))

    [log] = owned(ClaudeImporter).import_(path)
    assert [e.content for e in log.events] == ["- web_search: `news`\n\nNothing new."]


def _run(**changes) -> dict:
    """A scheduled task's run, as claude.ai keeps it: a chat opened by the task's prompt."""
    reply = [
        {"type": "tool_use", "name": "web_search", "input": {"query": "news"}},
        {"type": "text", "text": "Searched.\n[AI] Quiet in the lab"},
    ]
    follow_up = [
        {"type": "tool_use", "name": "web_fetch", "input": {"url": "https://example.com"}},
        {"type": "text", "text": "A holiday in the US."},
    ]
    messages = [
        {"sender": "human", "text": "Find news.", "created_at": "2026-11-21T18:11:05Z"},
        {"sender": "assistant", "text": "", "content": reply, "created_at": "2026-11-21T18:11:07Z", "stop_reason": "end_turn"},
        {"sender": "human", "text": "Why so quiet?", "created_at": "2026-11-21T19:01:40Z"},
        {"sender": "assistant", "text": "", "content": follow_up, "created_at": "2026-11-21T19:02:11Z", "stop_reason": "end_turn"},
    ]  # fmt: skip
    run = {
        "uuid": "run",
        "name": "⚡ Evening digest",
        "model": "claude-opus-5-5",
        "platform": "ROUTINE_RUN",
        "created_at": "2026-11-21T18:11:05.485293Z",
        "chat_messages": messages,
    }
    return run | changes


def _imported(tmp_path, *threads: dict) -> list:
    path = write_archive(
        tmp_path / "claude-wire.jsonl.xz",
        "claude",
        [{"endpoint": "conversation", "cid": t["uuid"], "response": json.dumps(t)} for t in threads],
    )
    return owned(ClaudeImporter).import_(path)


def test_wire_importer_run_opens_with_its_output_then_reads_on(tmp_path):
    """As claude-tasks reads a run: the prompt and the scheduled turn's tool calls stay in the archive."""
    [log] = _imported(tmp_path, _run())
    assert [(e.sender, e.content) for e in log.events] == [
        (Role.AGENT, "Searched.\n[AI] Quiet in the lab"),
        (Role.USER, "Why so quiet?"),
        (Role.AGENT, "- web_fetch: `https://example.com`\n\nA holiday in the US."),
    ]


def test_wire_importer_run_is_titled_by_its_headline(tmp_path):
    [log] = _imported(tmp_path, _run())
    assert log.title == "[AI] Quiet in the lab"


def test_wire_importer_run_without_a_headline_is_titled_by_task_and_time(tmp_path):
    run = _run()
    run["chat_messages"][1]["content"][-1]["text"] = "Searched."
    [log] = _imported(tmp_path, run)
    assert log.title == "Evening digest 18:11"


def test_wire_importer_run_names_its_task(tmp_path):
    [log] = _imported(tmp_path, _run())
    assert log.metadata["task"] == "Evening digest"


def test_wire_importer_run_still_replying_is_skipped(tmp_path):
    """Its reply ends with a `stop_reason`; until then the next fetch brings it back."""
    run = _run()
    del run["chat_messages"][1]["stop_reason"]
    assert [log.metadata["uuid"] for log in _imported(tmp_path, run, _THREAD)] == ["abc"]


def test_wire_importer_reads_legacy_parsed_responses(tmp_path, write_jsonl_gz):
    """v1 archives have no header and hold `response` already parsed. They are
    committed in users' repos, so they must still import."""
    path = write_jsonl_gz(tmp_path / "claude-wire.jsonl.gz", _entries(_THREAD))

    logs = owned(ClaudeImporter).import_(path)
    assert len(logs) == 1
    assert [e.content for e in logs[0].events] == ["hello", "hi back"]


def test_wire_importer_without_a_model_records_no_models(tmp_path):
    path = write_archive(tmp_path / "claude-wire.jsonl.gz", "claude", _entries(json.dumps(_THREAD)))

    [log] = owned(ClaudeImporter).import_(path)
    assert "models" not in log.metadata


def test_wire_importer_names_a_fallback_target_once(tmp_path):
    hop = {"from_model": {"model": "claude-fable-5"}, "to_model": {"model": "claude-opus-4-8"}}
    thread = {**_THREAD, "model": "claude-opus-4-8", "settings": {"safeguard_fallback": {"hops": [hop]}}}
    path = write_archive(tmp_path / "claude-wire.jsonl.gz", "claude", _entries(json.dumps(thread)))

    [log] = owned(ClaudeImporter).import_(path)
    assert log.metadata["models"] == ["claude-fable-5", "claude-opus-4-8"]


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
        logs = owned(ClaudeImporter).import_(path)

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
        logs = owned(ClaudeImporter).import_(path)

    assert logs[0].events[0].content == ""
    assert not [r for r in caplog.records if "no content or text" in r.message]


def test_export_importer_requires_users_json(tmp_path):
    """A ZIP with only conversations.json (like ChatGPT's export) is rejected."""
    path = tmp_path / "not-claude.zip"
    with ZipFile(path, "w") as zf:
        zf.writestr("conversations.json", "[]")
    assert not owned(ClaudeExportImporter).can_import(path)


def test_export_importer_accepts_full_pair(tmp_path):
    path = tmp_path / "claude-export.zip"
    with ZipFile(path, "w") as zf:
        zf.writestr("conversations.json", "[]")
        zf.writestr("users.json", "[]")
    assert owned(ClaudeExportImporter).can_import(path)


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

    logs = owned(ClaudeExportImporter).import_(path)
    assert logs[0].events[0].content == "real user text"
