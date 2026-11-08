"""Statistics and visualization for commonplace repository."""

from collections import Counter
from pathlib import Path

from rich.console import Console
from rich.table import Table

from commonplace._heatmap import ActivityHeatmap, build_activity_data, render_all_time_heatmap
from commonplace._repo import Commonplace
from commonplace._sources import source_holding


def source(path: Path) -> str:
    """The folder a note counts under: the tree of the source that holds it, or its top-level folder."""
    if held := source_holding(path):
        return held.tree.as_posix()
    return path.parts[0] if len(path.parts) > 1 else "misc"


def generate_stats(
    repo: Commonplace,
    sources: list[str] | None = None,
    all_time: bool = False,
    console: Console | None = None,
) -> tuple[str, str]:
    """
    Generate activity heatmap and stats table for a repository.

    Args:
        repo: The commonplace repository
        sources: Optional list of sources to filter by
        all_time: If True, show full history; otherwise show last 52 weeks
        console: Console to render with; defaults to one detecting the ambient terminal

    Returns:
        Tuple of (heatmap_output, table_output) as strings
    """

    if console is None:
        console = Console()

    console.print(f"[bold]Statistics for {repo.root}[/bold]", highlight=False)
    console.print()

    # Helper function for source prefix matching (e.g., "chats" matches "chats/claude")
    def matches_any_source(source_str: str) -> bool:
        return sources is None or any(source_str == src or source_str.startswith(src + "/") for src in sources)

    # Collect all note paths
    all_note_paths = list(repo.note_paths())

    # Filter by sources if specified
    note_paths = [path for path in all_note_paths if matches_any_source(source(path.path))]
    if not note_paths and sources is not None:
        raise ValueError(f"No notes found for sources: {', '.join(sources)}")

    # Build activity heatmap
    activity = build_activity_data(note_paths)
    heatmap_output = ""

    if activity:
        # Build title suffix for filtered sources
        source_suffix = ""
        if sources:
            source_suffix = f" - {', '.join(sources)}" if len(sources) > 1 else f" - {sources[0]}"

        # Capture heatmap output
        with console.capture() as capture:
            if all_time:
                title = f"Activity (all time){source_suffix}"
                console.print(f"[bold]{title}[/bold]", highlight=False)
                render_all_time_heatmap(activity, console)
            else:
                title = f"Activity (last 52 weeks){source_suffix}"
                console.print(f"[bold]{title}[/bold]", highlight=False)
                heatmap = ActivityHeatmap(activity, weeks=52)
                console.print(heatmap)
            console.print()

        heatmap_output = capture.get()

    # Build stats table
    repo_counts: Counter[str] = Counter()
    repo_counts.update(source(path.path) for path in note_paths)

    index_chunks_by_source: Counter[str] = Counter()
    all_stats = list(repo.index.stats())

    # Filter index stats by sources if specified
    if sources:
        filtered_stats = [stat for stat in all_stats if matches_any_source(source(stat.repo_path.path))]
    else:
        filtered_stats = all_stats

    for stat in filtered_stats:
        index_chunks_by_source.update({source(stat.repo_path.path): stat.num_chunks})

    sources_list = sorted(
        set(repo_counts) | set(index_chunks_by_source),
        key=lambda category: (-repo_counts.get(category, 0), category),
    )

    # Build table
    table = Table("Source", "Files", "Indexed chunks")
    repo_total = sum(repo_counts.values(), 0)
    index_total = sum(index_chunks_by_source.values(), 0)

    def make_percentage(val, total):
        return f"{val:<6,} [dim]{val / total:>6.1%}[/]" if total > 0 else "0"

    # Add a row for each source
    for name in sources_list:
        repo_count = repo_counts.get(name, 0)
        index_count = index_chunks_by_source.get(name, 0)
        table.add_row(
            name,
            make_percentage(repo_count, repo_total),
            make_percentage(index_count, index_total),
        )

    # Add total row
    table.add_section()
    table.add_row("Total", make_percentage(repo_total, repo_total), make_percentage(index_total, index_total))

    # Capture table output
    with console.capture() as capture:
        console.print(table)

    table_output = capture.get()

    return heatmap_output, table_output
