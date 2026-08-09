"""Tests for activity heatmap."""

from collections import Counter
from datetime import date, timedelta
from pathlib import Path

import pytest

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

    # Counts climb the ramp: no activity, the three intensity levels, then the max marker
    expected = {0: "░", 1: "▒", 2: "▓", 3: "█", 5: "*"}

    assert {count: heatmap._get_style_and_char(count)[1] for count in expected} == expected


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
    _style, char = heatmap._get_style_and_char(1)
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
    _style, char = heatmap._get_style_and_char(10)
    assert char == "*"

    # Last level should be max with red color
    assert heatmap.levels[-1][0] == 10
    assert heatmap.levels[-1][2] == "*"


@pytest.mark.parametrize("end_date", [date(2024, 1, 14) + timedelta(days=n) for n in range(7)])
def test_activity_heatmap_grid_reaches_end_date(end_date):
    """
    The grid has to reach end_date, whatever weekday it falls on.

    Columns are week-aligned, so aligning them to the start of the window instead leaves the grid ending
    short of end_date — and with end_date defaulting to today, the days lost are the most recent ones.
    Parametrized over every weekday so no alignment gets special treatment.
    """
    heatmap = ActivityHeatmap(Counter({end_date: 1}), end_date=end_date, weeks=52)

    placed = {day for row in heatmap.grid for day, _count in row}
    window = {heatmap.start_date + timedelta(days=n) for n in range((end_date - heatmap.start_date).days + 1)}

    assert end_date in placed
    assert len(heatmap.grid[0]) == 52  # still 52 week columns, not 53
    assert window <= placed, f"missing from grid: {sorted(window - placed)}"


def test_activity_heatmap_renders_the_busiest_day(sample_activity, any_terminal):
    """The max marker has to reach the output, not just the legend, in either rendering mode."""
    heatmap = ActivityHeatmap(sample_activity, end_date=date(2024, 1, 20), weeks=52)

    with any_terminal.capture() as capture:
        any_terminal.print(heatmap)

    grid, _sep, _legend = capture.get().rpartition("Less")

    assert "*" in grid


def test_activity_heatmap_levels_have_distinct_glyphs():
    """Intensity has to survive without colour, since piped and headless output carries no styling."""
    activity = Counter({date(2024, 1, 1): 1, date(2024, 1, 2): 5, date(2024, 1, 3): 9})
    heatmap = ActivityHeatmap(activity, end_date=date(2024, 1, 31), weeks=4)

    glyphs = [char for _threshold, _style, char in heatmap.levels]

    assert len(set(glyphs)) == len(glyphs), f"levels share a glyph: {glyphs}"


def test_activity_heatmap_renders_per_terminal(sample_activity, any_terminal, snapshot):
    """
    Pin the 52-week rendering in each terminal mode.

    The window is a view concern — `end_date` pins it here — so this needs no cooperation from the caller
    to be reproducible.
    """
    heatmap = ActivityHeatmap(sample_activity, end_date=date(2024, 1, 20), weeks=52)

    with any_terminal.capture() as capture:
        any_terminal.print(heatmap)

    snapshot.assert_match(capture.get(), snapshot_name="heatmap.txt")


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
