"""GitHub-style activity heatmap visualization."""

import re
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

from rich.console import Console, ConsoleOptions, RenderResult
from rich.measure import Measurement
from rich.segment import Segment
from rich.style import Style

from commonplace._types import RepoPath


def extract_date_from_path(path: Path) -> date | None:
    """
    Extract date from a note path.

    Supports patterns like:
    - journal/YYYY/MM/YYYY-MM-DD.md
    - chats/source/YYYY/MM/YYYY-MM-DD-title.md

    Args:
        path: Path to extract date from

    Returns:
        Date if found, None otherwise
    """
    # Look for YYYY-MM-DD pattern in the filename
    match = re.search(r"(\d{4})-(\d{2})-(\d{2})", path.name)
    if match:
        try:
            return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            return None
    return None


def build_activity_data(note_paths: list[RepoPath]) -> Counter[date]:
    """
    Build activity data from note paths.

    Args:
        note_paths: List of note paths to analyze

    Returns:
        Counter mapping dates to number of notes created on that date
    """
    activity: Counter[date] = Counter()
    for repo_path in note_paths:
        note_date = extract_date_from_path(repo_path.path)
        if note_date:
            activity[note_date] += 1
    return activity


class ActivityHeatmap:
    """GitHub-style activity heatmap visualization."""

    def __init__(self, activity: Counter[date], end_date: date | None = None, weeks: int = 52):
        """
        Create an activity heatmap.

        Args:
            activity: Counter mapping dates to activity counts
            end_date: End date for heatmap (default: today)
            weeks: Number of weeks to show (default: 52)
        """
        self.activity = activity
        self.end_date = end_date or date.today()
        self.weeks = weeks

        # Calculate start date (weeks * 7 days before end_date)
        self.start_date = self.end_date - timedelta(days=weeks * 7 - 1)

        # Build the grid (7 rows for days of week, weeks columns)
        self.grid = self._build_grid()

        # Define intensity levels (like GitHub)
        # Calculate quartiles from the data for dynamic levels
        if activity:
            values = [count for count in activity.values() if count > 0]
            if values:
                values_sorted = sorted(values)
                q1 = values_sorted[len(values_sorted) // 4] if len(values_sorted) > 4 else 1
                q2 = values_sorted[len(values_sorted) // 2] if len(values_sorted) > 2 else 2
                q3 = values_sorted[3 * len(values_sorted) // 4] if len(values_sorted) > 4 else 3
            else:
                q1, q2, q3 = 1, 2, 3
        else:
            q1, q2, q3 = 1, 2, 3

        self.levels = [
            (0, Style(color="grey30"), "░"),  # No activity
            (1, Style(color="#0e4429"), "▓"),  # Low (1st quartile) - GitHub dark green
            (q2, Style(color="#006d32"), "▓"),  # Medium (median) - GitHub medium green
            (q3, Style(color="#26a641"), "█"),  # High (3rd quartile) - GitHub bright green
        ]
        self.q1, self.q2, self.q3 = q1, q2, q3

    def _build_grid(self) -> list[list[tuple[date, int]]]:
        """Build the heatmap grid."""
        # Start from the first day of the week containing start_date
        # (GitHub starts weeks on Sunday)
        current = self.start_date - timedelta(days=self.start_date.weekday() + 1)  # Go to Sunday

        grid = [[] for _ in range(7)]  # 7 rows (Sun-Sat)

        for _ in range(self.weeks):
            for day in range(7):
                grid[day].append((current, self.activity.get(current, 0)))
                current += timedelta(days=1)

        return grid

    def _get_style_and_char(self, count: int) -> tuple[Style, str]:
        """Get style and character for a given activity count."""
        for threshold, style, char in reversed(self.levels):
            if count >= threshold:
                return style, char
        return self.levels[0][1], self.levels[0][2]

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        """Render the heatmap using rich."""
        # Day labels (first column)
        day_labels = ["", "Mon", "", "Wed", "", "Fri", ""]

        # Month labels (top row) - show month when it changes
        month_labels = []
        current_month = None
        for week_idx in range(self.weeks):
            if week_idx < len(self.grid[0]):
                week_date = self.grid[0][week_idx][0]
                if week_date.month != current_month:
                    month_labels.append((week_idx, week_date.strftime("%b")))
                    current_month = week_date.month

        # Render month labels
        month_line = " " * 4  # Space for day labels
        for week_idx in range(self.weeks):
            # Check if this week has a month label
            label = ""
            for label_week, label_text in month_labels:
                if label_week == week_idx:
                    label = label_text
                    break
            if label:
                month_line += label + " " * (2 - len(label) + 1)
            else:
                month_line += "  "
        yield Segment(month_line + "\n")

        # Render heatmap grid
        for day_idx, row in enumerate(self.grid):
            segments = []

            # Add day label
            label = day_labels[day_idx]
            segments.append(Segment(f"{label:>3} "))

            # Add activity squares
            for day_date, count in row:
                if day_date < self.start_date or day_date > self.end_date:
                    segments.append(Segment("  "))  # Empty space for padding
                else:
                    style, char = self._get_style_and_char(count)
                    segments.append(Segment(f"{char} ", style))

            segments.append(Segment("\n"))
            yield from segments

        # Add legend
        yield Segment("\n")
        yield Segment("Less ", Style(dim=True))
        for threshold, style, char in self.levels:
            yield Segment(f"{char} ", style)
        yield Segment(" More", Style(dim=True))
        yield Segment("\n")

    def __rich_measure__(self, console: Console, options: ConsoleOptions) -> Measurement:
        """Measure the heatmap width."""
        width = 4 + self.weeks * 2  # day labels + 2 chars per week
        return Measurement(width, width)
