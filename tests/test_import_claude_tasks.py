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


def test_claude_tasks_run_opens_with_its_output_then_reads_on_in_sequence(run):
    """The prompt is a template, not something said that day, so the chat starts at what the run produced."""
    assert [(e.sender, e.content) for e in run.events if isinstance(e, Message)] == [
        (Role.AGENT, "[AI] Nothing new today"),
        (Role.USER, "Why not?"),
        (Role.AGENT, "A quiet night."),
    ]


def test_claude_tasks_run_leaves_out_the_work_behind_its_output(run):
    assert not [e for e in run.events if isinstance(e, ToolCall)]


def test_claude_tasks_run_without_output_yet_is_skipped(tmp_path):
    """A run caught mid-flight has nothing to show; its later events bring it back on the next fetch."""
    entries = list(read_entries(EXAMPLE))
    events = json.loads(entries[1]["response"])
    events["data"] = [e for e in events["data"] if int(e["sequence_num"]) < 7]
    archive = write_archive(
        tmp_path / "claude-tasks-wire.jsonl.gz",
        "claude-tasks",
        [entries[0], entries[1] | {"response": json.dumps(events)}],
    )

    assert ClaudeTasksImporter().import_(archive) == []


def test_claude_tasks_run_title_drops_decoration_and_carries_the_time(run):
    """Twice-daily runs share a title and a date, so the time keeps their paths apart."""
    assert run.title == "Morning digest 05:10"
    assert run.created == datetime(2026, 10, 11, 5, 10, 31, 312825, tzinfo=UTC)


def test_claude_tasks_run_metadata_ties_it_to_its_task(run):
    assert run.metadata == {
        "session_id": "cse_01Example",
        "trigger_id": "trig_01Example",
        "resource": "https://claude.ai/code/session_01Example",
        "models": ["claude-opus-5-5"],
    }
