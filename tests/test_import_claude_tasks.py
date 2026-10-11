"""Tests for the scheduled-run importer, driven by the committed example archive."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from commonplace._import._claude_tasks import ClaudeTasksImporter
from commonplace._import._commands import autodetect_importer
from commonplace._import._types import Message, Role, ToolCall
from commonplace._wire import read_entries, write_archive

WIRE = Path(__file__).parent / "resources" / "wire"
EXAMPLE = WIRE / "claude-tasks-v3.jsonl.gz"


@pytest.fixture
def run():
    [log] = ClaudeTasksImporter().import_(EXAMPLE)
    return log


def test_claude_tasks_archive_is_claimed_by_its_own_importer():
    assert isinstance(autodetect_importer(EXAMPLE), ClaudeTasksImporter)


@pytest.mark.parametrize("other", ["claude-v3", "claude-memory-v3"])
def test_claude_tasks_importer_declines_other_claude_archives(other):
    assert not ClaudeTasksImporter().can_import(WIRE / f"{other}.jsonl.gz")


def _rewritten(tmp_path, edit) -> Path:
    """The example archive with its events passed through `edit`."""
    entries = list(read_entries(EXAMPLE))
    events = json.loads(entries[1]["response"])
    events["data"] = edit(events["data"])
    return write_archive(
        tmp_path / "claude-tasks-wire.jsonl.gz",
        "claude-tasks",
        [entries[0], entries[1] | {"response": json.dumps(events)}],
    )


def test_claude_tasks_run_opens_with_its_output_then_reads_on_in_sequence(run):
    """The prompt is a template, not something said that day, so the chat starts at what the run produced.

    All of the scheduled turn's text, not just `result`: that repeats only the last of it, which can be a sign-off."""
    assert [(e.sender, e.content) for e in run.events if isinstance(e, Message)] == [
        (Role.AGENT, "Done.\n[AI] Nothing new today"),
        (Role.AGENT, "Log updated."),
        (Role.USER, "Why not?"),
        (Role.AGENT, "A quiet night."),
    ]


def test_claude_tasks_run_leaves_out_the_work_behind_its_output(run):
    assert not [e for e in run.events if isinstance(e, ToolCall)]


def test_claude_tasks_run_without_output_yet_is_skipped(tmp_path):
    """A run caught mid-flight has nothing to show; its later events bring it back on the next fetch."""
    archive = _rewritten(tmp_path, lambda events: [e for e in events if e["event_type"] != "result"])

    assert ClaudeTasksImporter().import_(archive) == []


def test_claude_tasks_run_is_titled_by_the_first_headline_in_its_output(run):
    """Narration can come before the headline, so it is searched for, not expected first."""
    assert run.title == "[AI] Nothing new today"


def test_claude_tasks_run_without_a_headline_is_titled_by_task_and_time(tmp_path):
    """Twice-daily runs share a task and a date, so the time keeps their paths apart; the decoration is dropped."""

    def unheadline(events):
        for event in events:
            if event["sequence_num"] == "6":
                event["payload"]["message"]["content"][0]["text"] = "Nothing new today, see [the log](x)."
        return events

    [log] = ClaudeTasksImporter().import_(_rewritten(tmp_path, unheadline))
    assert log.title == "Morning digest 05:10"


def test_claude_tasks_run_is_dated_by_when_it_started(run):
    assert run.created == datetime(2026, 10, 11, 5, 10, 31, 312825, tzinfo=UTC)


def test_claude_tasks_run_metadata_ties_it_to_its_task(run):
    assert run.metadata == {
        "task": "Morning digest",
        "session_id": "cse_01Example",
        "trigger_id": "trig_01Example",
        "resource": "https://claude.ai/code/session_01Example",
        "models": ["claude-opus-5-5"],
    }
