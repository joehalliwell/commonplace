"""Statistics and visualization for commonplace repository."""

from collections import Counter

from rich.console import Console
from rich.table import Table

from commonplace._heatmap import ActivityHeatmap, build_activity_data, render_all_time_heatmap
from commonplace._repo import Commonplace


def generate_stats(
    repo: Commonplace,
    sources: list[str] | None = None,
    all_time: bool = False,
) -> tuple[str, str]:
    """
    Generate activity heatmap and stats table for a repository.

    Args:
        repo: The commonplace repository
        sources: Optional list of sources to filter by
        all_time: If True, show full history; otherwise show last 52 weeks

    Returns:
        Tuple of (heatmap_output, table_output) as strings
    """

    console = Console()

    console.print(f"[bold]Statistics for {repo.root}[/bold]")
    console.print()

    # Helper function for source prefix matching (e.g., "chats" matches "chats/claude")
    def matches_any_source(source_str: str) -> bool:
        return any(source_str == src or source_str.startswith(src + "/") for src in sources)

    # Collect all note paths
    all_note_paths = list(repo.note_paths())

    # Filter by sources if specified
    if sources:
        note_paths = [path for path in all_note_paths if matches_any_source(repo.config.source(path))]
        if not note_paths:
            raise ValueError(f"No notes found for sources: {', '.join(sources)}")
    else:
        note_paths = all_note_paths

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
                console.print(f"[bold]{title}[/bold]")
                render_all_time_heatmap(activity, console)
            else:
                title = f"Activity (last 52 weeks){source_suffix}"
                console.print(f"[bold]{title}[/bold]")
                heatmap = ActivityHeatmap(activity, weeks=52)
                console.print(heatmap)
            console.print()

        heatmap_output = capture.get()

    # Build stats table
    repo_counts: Counter[str] = Counter()
    repo_counts.update(repo.config.source(path) for path in note_paths)

    index_chunks_by_source: Counter[str] = Counter()
    all_stats = list(repo.index.stats())

    # Filter index stats by sources if specified
    if sources:
        filtered_stats = [stat for stat in all_stats if matches_any_source(repo.config.source(stat.repo_path))]
    else:
        filtered_stats = all_stats

    for stat in filtered_stats:
        index_chunks_by_source.update({repo.config.source(stat.repo_path): stat.num_chunks})

    sources_list = sorted(
        set(repo_counts) | set(index_chunks_by_source),
        key=lambda category: -repo_counts.get(category, 0),
    )

    # Build table
    table = Table("Source", "Files", "Indexed chunks")
    repo_total = sum(repo_counts.values(), 0)
    index_total = sum(index_chunks_by_source.values(), 0)

    def make_percentage(val, total):
        return f"{val:<6,} [dim]{val / total:>6.1%}[/]" if total > 0 else "0"

    # Add a row for each source
    for source in sources_list:
        repo_count = repo_counts.get(source, 0)
        index_count = index_chunks_by_source.get(source, 0)
        table.add_row(
            source,
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
