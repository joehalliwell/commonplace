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

    # Should have 5 levels (0 + 3 intensity levels + max)
    assert len(heatmap.levels) == 5

    # Check that levels are sorted by threshold
    thresholds = [level[0] for level in heatmap.levels]
    assert thresholds == sorted(thresholds)


def test_activity_heatmap_style_selection():
    """Test that correct style is selected for different counts."""
    activity = Counter({date(2024, 1, 1): 5})
    heatmap = ActivityHeatmap(activity, end_date=date(2024, 1, 31), weeks=4)

    # Test different activity counts
    style_0, char_0 = heatmap._get_style_and_char(0)
    assert char_0 == "░"  # No activity

    style_1, char_1 = heatmap._get_style_and_char(1)
    assert char_1 == "█"  # Activity

    style_max, char_max = heatmap._get_style_and_char(5)
    assert char_max == "*"  # Max activity gets special char


def test_activity_heatmap_thresholds_start_at_one():
    """Test that first non-zero threshold starts at 1."""
    activity = Counter({date(2024, 1, 1): 5, date(2024, 1, 2): 10})
    heatmap = ActivityHeatmap(activity, end_date=date(2024, 1, 31), weeks=4)

    # Extract thresholds from levels (skip the 0 level)
    thresholds = [level[0] for level in heatmap.levels if level[0] > 0]
    assert thresholds[0] == 1


def test_activity_heatmap_max_count_one_gets_highest_intensity():
    """Test that when max count is 1, it gets the highest intensity."""
    activity = Counter({date(2024, 1, 1): 1})
    heatmap = ActivityHeatmap(activity, end_date=date(2024, 1, 31), weeks=4)

    # Count of 1 should get the max intensity (*)
    style, char = heatmap._get_style_and_char(1)
    assert char == "*"


def test_activity_heatmap_max_gets_special_marker():
    """Test that max value gets special red asterisk marker."""
    activity = Counter(
        {
            date(2024, 1, 1): 1,
            date(2024, 1, 2): 5,
            date(2024, 1, 3): 10,
        }
    )
    heatmap = ActivityHeatmap(activity, end_date=date(2024, 1, 31), weeks=4)

    # Max value should get the special marker
    style, char = heatmap._get_style_and_char(10)
    assert char == "*"

    # Last level should be max with red color
    assert heatmap.levels[-1][0] == 10
    assert heatmap.levels[-1][2] == "*"


def test_activity_heatmap_custom_num_levels():
    """Test that custom number of levels works correctly."""
    activity = Counter(
        {
            date(2024, 1, 1): 1,
            date(2024, 1, 2): 10,
        }
    )
    heatmap = ActivityHeatmap(activity, end_date=date(2024, 1, 31), weeks=4, num_levels=5)

    # Should have 7 levels total (0 + 5 intensity levels + max)
    assert len(heatmap.levels) == 7

    # Last level should be max
    assert heatmap.levels[-1][0] == 10
    assert heatmap.levels[-1][2] == "*"
