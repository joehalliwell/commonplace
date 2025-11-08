"""Tests for activity heatmap."""

from collections import Counter
from datetime import date
from pathlib import Path

from commonplace._heatmap import ActivityHeatmap, build_activity_data, extract_date_from_path
from commonplace._types import RepoPath


def test_extract_date_from_path_journal():
    """Test extracting date from journal path."""
    path = Path("journal/2024/01/2024-01-15.md")
    result = extract_date_from_path(path)
    assert result == date(2024, 1, 15)


def test_extract_date_from_path_chat():
    """Test extracting date from chat path."""
    path = Path("chats/claude/2024/03/2024-03-20-conversation-title.md")
    result = extract_date_from_path(path)
    assert result == date(2024, 3, 20)


def test_extract_date_from_path_no_date():
    """Test extracting date from path without date."""
    path = Path("notes/random-note.md")
    result = extract_date_from_path(path)
    assert result is None


def test_extract_date_from_path_invalid_date():
    """Test extracting invalid date from path."""
    path = Path("notes/2024-13-99-invalid.md")
    result = extract_date_from_path(path)
    assert result is None


def test_build_activity_data():
    """Test building activity data from note paths."""
    note_paths = [
        RepoPath(path=Path("journal/2024/01/2024-01-15.md"), ref="abc123"),
        RepoPath(path=Path("journal/2024/01/2024-01-15.md"), ref="def456"),  # Same day
        RepoPath(path=Path("journal/2024/01/2024-01-16.md"), ref="ghi789"),
        RepoPath(path=Path("notes/no-date.md"), ref="jkl012"),  # No date
    ]

    activity = build_activity_data(note_paths)

    assert activity[date(2024, 1, 15)] == 2
    assert activity[date(2024, 1, 16)] == 1
    assert len(activity) == 2  # Only two unique dates


def test_activity_heatmap_grid_dimensions():
    """Test that heatmap grid has correct dimensions."""
    activity = Counter({date(2024, 1, 15): 3})
    heatmap = ActivityHeatmap(activity, end_date=date(2024, 1, 20), weeks=4)

    # Grid should have 7 rows (days of week)
    assert len(heatmap.grid) == 7

    # Each row should have 4 weeks of data
    for row in heatmap.grid:
        assert len(row) == 4


def test_activity_heatmap_intensity_levels():
    """Test that heatmap has correct intensity levels."""
    activity = Counter(
        {
            date(2024, 1, 1): 1,
            date(2024, 1, 2): 2,
            date(2024, 1, 3): 3,
            date(2024, 1, 4): 5,
            date(2024, 1, 5): 10,
        }
    )
    heatmap = ActivityHeatmap(activity, end_date=date(2024, 1, 31), weeks=4)

    # Should have 4 levels (0, low, medium, high)
    assert len(heatmap.levels) == 4

    # Check that thresholds are calculated
    assert heatmap.q1 > 0
    assert heatmap.q2 > 0
    assert heatmap.q3 > 0


def test_activity_heatmap_style_selection():
    """Test that correct style is selected for different counts."""
    activity = Counter({date(2024, 1, 1): 5})
    heatmap = ActivityHeatmap(activity, end_date=date(2024, 1, 31), weeks=4)

    # Test different activity counts
    style_0, char_0 = heatmap._get_style_and_char(0)
    assert char_0 == "░"  # No activity

    style_1, char_1 = heatmap._get_style_and_char(1)
    assert char_1 == "▓"  # Low activity

    style_high, char_high = heatmap._get_style_and_char(10)
    assert char_high == "█"  # High activity
