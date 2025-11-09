"""Tests for stats generation."""

from pathlib import Path

import pytest

from commonplace._stats import generate_stats
from commonplace._types import Note, RepoPath


def test_generate_stats_basic(test_repo):
    """Test basic stats generation."""
    # Add some test notes
    test_repo.save(Note(RepoPath(Path("journal/2024/01/2024-01-15.md"), ""), "# Test journal\n\nSome content"))
    test_repo.save(Note(RepoPath(Path("journal/2024/01/2024-01-16.md"), ""), "# Another journal\n\nMore content"))
    test_repo.save(Note(RepoPath(Path("notes/general.md"), ""), "# General note\n\nStuff"))

    # Generate stats
    heatmap_output, table_output = generate_stats(test_repo, sources=None, all_time=False)

    # Check that we got output
    assert heatmap_output  # Should have heatmap since we have dated notes
    assert table_output
    assert "Activity (last 52 weeks)" in heatmap_output
    assert "journal" in table_output
    assert "notes" in table_output
    assert "Total" in table_output


def test_generate_stats_with_source_filter(test_repo):
    """Test stats generation with source filtering."""
    # Add notes in different sources
    test_repo.save(Note(RepoPath(Path("journal/2024/01/2024-01-15.md"), ""), "# Journal\n\nContent"))
    test_repo.save(Note(RepoPath(Path("notes/general.md"), ""), "# Note\n\nContent"))

    # Filter by journal source
    heatmap_output, table_output = generate_stats(test_repo, sources=["journal"], all_time=False)

    # Check filtering
    assert "journal" in heatmap_output  # Should show in title
    assert "journal" in table_output


def test_generate_stats_with_multiple_sources(test_repo):
    """Test stats generation with multiple source filters."""
    # Add notes in different sources
    test_repo.save(Note(RepoPath(Path("journal/2024/01/2024-01-15.md"), ""), "# Journal\n\nContent"))
    test_repo.save(Note(RepoPath(Path("chats/claude/2024/01/2024-01-16.md"), ""), "# Chat\n\nContent"))
    test_repo.save(Note(RepoPath(Path("notes/general.md"), ""), "# Note\n\nContent"))

    # Filter by journal and chats/claude sources (chats source includes provider)
    heatmap_output, table_output = generate_stats(test_repo, sources=["journal", "chats/claude"], all_time=False)

    # Check filtering
    assert "journal" in heatmap_output  # Should show in title
    assert "journal" in table_output
    assert "chats/claude" in table_output


def test_generate_stats_with_prefix_matching(test_repo):
    """Test stats generation with prefix matching (e.g., 'chats' matches 'chats/claude')."""
    # Add notes in different chat sources
    test_repo.save(Note(RepoPath(Path("chats/claude/2024/01/2024-01-15.md"), ""), "# Claude chat\n\nContent"))
    test_repo.save(Note(RepoPath(Path("chats/gemini/2024/01/2024-01-16.md"), ""), "# Gemini chat\n\nContent"))
    test_repo.save(Note(RepoPath(Path("journal/2024/01/2024-01-17.md"), ""), "# Journal\n\nContent"))

    # Filter by "chats" prefix - should match both chat sources
    heatmap_output, table_output = generate_stats(test_repo, sources=["chats"], all_time=False)

    # Check that both chat sources are included
    assert "chats" in heatmap_output
    assert "chats/claude" in table_output
    assert "chats/gemini" in table_output
    # Journal should not be included
    assert "journal" not in table_output


def test_generate_stats_all_time(test_repo):
    """Test stats generation with all-time view."""
    # Add notes from different years
    test_repo.save(Note(RepoPath(Path("journal/2023/01/2023-01-15.md"), ""), "# Old journal\n\nContent"))
    test_repo.save(Note(RepoPath(Path("journal/2024/01/2024-01-15.md"), ""), "# New journal\n\nContent"))

    # Generate all-time stats
    heatmap_output, table_output = generate_stats(test_repo, sources=None, all_time=True)

    # Check that we got output with all-time view
    assert heatmap_output
    assert "Activity (all time)" in heatmap_output
    assert "2023" in heatmap_output
    assert "2024" in heatmap_output
    assert table_output


def test_generate_stats_invalid_source(test_repo):
    """Test stats generation with invalid source filter."""
    # Add a note
    test_repo.save(Note(RepoPath(Path("journal/2024/01/2024-01-15.md"), ""), "# Journal\n\nContent"))

    # Try to filter by non-existent source
    with pytest.raises(ValueError, match="No notes found for sources: invalid"):
        generate_stats(test_repo, sources=["invalid"], all_time=False)


def test_generate_stats_no_dated_notes(test_repo):
    """Test stats generation when there are no dated notes."""
    # Add only notes without dates
    test_repo.save(Note(RepoPath(Path("notes/general.md"), ""), "# Note\n\nContent"))

    # Generate stats
    heatmap_output, table_output = generate_stats(test_repo, sources=None, all_time=False)

    # Should have no heatmap but still have table
    assert heatmap_output == ""
    assert table_output
    assert "notes" in table_output


def test_generate_stats_empty_repo(test_repo):
    """Test stats generation on empty repository."""
    # Generate stats on empty repo
    heatmap_output, table_output = generate_stats(test_repo, sources=None, all_time=False)

    # Should have no heatmap and minimal table
    assert heatmap_output == ""
    assert table_output
    assert "Total" in table_output


def test_generate_stats_with_indexed_content(test_repo):
    """Test stats generation includes indexed chunks."""
    # Add and index a note
    test_repo.save(
        Note(
            RepoPath(Path("notes/test.md"), ""),
            "# Test\n\n## Section 1\n\nContent here.\n\n## Section 2\n\nMore content.",
        )
    )
    test_repo.commit("Add test note", auto_index=False)

    # Index the note
    from commonplace._search._commands import index

    index(test_repo, rebuild=True)

    # Generate stats
    heatmap_output, table_output = generate_stats(test_repo, sources=None, all_time=False)

    # Check that indexed chunks are shown
    assert table_output
    assert "Indexed chunks" in table_output
    # Should show some chunks indexed for the notes source
