"""Tests for repository statistics."""

from datetime import datetime
from pathlib import Path

import pytest

from commonplace._repo import Commonplace
from commonplace._types import Note, RepoPath


@pytest.fixture
def temp_commonplace(tmp_path):
    """Fixture to create a temporary Commonplace directory."""
    Commonplace.init(tmp_path)
    repo = Commonplace.open(tmp_path)
    repo.commit("Initialize test repository")
    return repo


def test_stats_empty_repo(temp_commonplace):
    """Test stats on an empty repository."""
    stats = temp_commonplace.stats()

    assert stats.num_notes == 0
    assert stats.total_size_bytes == 0
    assert stats.providers == {}
    assert stats.oldest_timestamp == 0
    assert stats.newest_timestamp == 0


def test_stats_single_note(temp_commonplace):
    """Test stats with a single note."""
    # Create a note with a date in the filename
    note_path = RepoPath(path=Path("chats/claude/2024/01/2024-01-15-test-note.md"), ref=temp_commonplace.head_ref)
    content = "# Test Note\n\nThis is a test."
    note = Note(repo_path=note_path, content=content)

    temp_commonplace.save(note)
    temp_commonplace.commit("Add test note")

    stats = temp_commonplace.stats()

    assert stats.num_notes == 1
    assert stats.total_size_bytes == len(content)
    assert stats.providers == {"claude": 1}

    # Check timestamp (2024-01-15)
    expected_timestamp = int(datetime(2024, 1, 15).timestamp())
    assert stats.oldest_timestamp == expected_timestamp
    assert stats.newest_timestamp == expected_timestamp


def test_stats_multiple_notes_multiple_providers(temp_commonplace):
    """Test stats with multiple notes from different providers."""
    notes = [
        ("chats/claude/2024/01/2024-01-15-first.md", "# First\n\nClaude note.", "claude", datetime(2024, 1, 15)),
        ("chats/gemini/2024/02/2024-02-20-second.md", "# Second\n\nGemini note.", "gemini", datetime(2024, 2, 20)),
        (
            "chats/chatgpt/2024/03/2024-03-10-third.md",
            "# Third\n\nChatGPT note.",
            "chatgpt",
            datetime(2024, 3, 10),
        ),
        ("chats/claude/2024/04/2024-04-01-fourth.md", "# Fourth\n\nAnother Claude.", "claude", datetime(2024, 4, 1)),
    ]

    total_size = 0
    for path_str, content, _, _ in notes:
        note_path = RepoPath(path=Path(path_str), ref=temp_commonplace.head_ref)
        note = Note(repo_path=note_path, content=content)
        temp_commonplace.save(note)
        total_size += len(content)

    temp_commonplace.commit("Add multiple notes")

    stats = temp_commonplace.stats()

    assert stats.num_notes == 4
    assert stats.total_size_bytes == total_size
    assert stats.providers == {"claude": 2, "gemini": 1, "chatgpt": 1}

    # Oldest should be 2024-01-15, newest should be 2024-04-01
    assert stats.oldest_timestamp == int(datetime(2024, 1, 15).timestamp())
    assert stats.newest_timestamp == int(datetime(2024, 4, 1).timestamp())


def test_stats_note_without_date(temp_commonplace):
    """Test stats with a note that doesn't have a valid date in filename."""
    note_path = RepoPath(path=Path("chats/claude/no-date-note.md"), ref=temp_commonplace.head_ref)
    content = "# No Date Note\n\nThis note has no date."
    note = Note(repo_path=note_path, content=content)

    temp_commonplace.save(note)
    temp_commonplace.commit("Add note without date")

    stats = temp_commonplace.stats()

    assert stats.num_notes == 1
    assert stats.total_size_bytes == len(content)
    assert stats.providers == {"claude": 1}
    # No valid timestamp extracted
    assert stats.oldest_timestamp == 0
    assert stats.newest_timestamp == 0


def test_stats_note_outside_chats_dir(temp_commonplace):
    """Test stats with a note outside the chats directory."""
    note_path = RepoPath(path=Path("random/2024-01-15-note.md"), ref=temp_commonplace.head_ref)
    content = "# Random Note\n\nOutside chats dir."
    note = Note(repo_path=note_path, content=content)

    temp_commonplace.save(note)
    temp_commonplace.commit("Add random note")

    stats = temp_commonplace.stats()

    assert stats.num_notes == 1
    assert stats.total_size_bytes == len(content)
    # No provider extracted (not in chats/...)
    assert stats.providers == {}
    # But timestamp should still be extracted
    assert stats.oldest_timestamp == int(datetime(2024, 1, 15).timestamp())
    assert stats.newest_timestamp == int(datetime(2024, 1, 15).timestamp())
