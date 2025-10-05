from collections import Counter
import logging
from pathlib import Path

import typer
from rich.logging import RichHandler

from commonplace import get_config, logger
from commonplace._repo import Commonplace
from commonplace._search._types import SearchMethod

app = typer.Typer(
    help="Commonplace: Personal knowledge management",
    pretty_exceptions_enable=False,
)


@app.callback()
def _setup_logging(verbose: bool = typer.Option(False, "--verbose", "-v")):
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.addHandler(RichHandler())


@app.command(name="import")
def import_(path: Path):
    """Import AI conversation exports (Claude ZIP, Gemini Takeout) into your commonplace."""

    config = get_config()
    repo = Commonplace.open(config.root)

    from commonplace._import._commands import import_

    import_(path, repo, user=config.user, prefix="chats")


@app.command()
def init():
    """Initialize a commonplace working directory."""
    config = get_config()
    Commonplace.init(config.root)


@app.command()
def index(rebuild: bool = typer.Option(False, "--rebuild", help="Rebuild the index from scratch")):
    """Build or rebuild the search index for semantic search."""
    config = get_config()

    from commonplace._search._commands import index

    index(config.get_repo(), config.get_index(), rebuild=rebuild)


@app.command()
def search(
    query: str,
    limit: int = typer.Option(10, "--limit", "-n", help="Maximum number of results"),
    method: SearchMethod = typer.Option(
        SearchMethod.HYBRID, "--method", help="Search method: semantic, keyword, or hybrid"
    ),
    model: str = typer.Option("3-small", "--model", "-m", help="LLM embedding model ID"),
):
    """Search for semantically similar content in your commonplace."""
    config = get_config()

    index = config.get_index()
    results = index.search(query, limit=limit, method=method)

    if not results:
        logger.info("No results found")
        return

    # Display results
    for i, hit in enumerate(results, 1):
        print(f"\n{i}. {hit.chunk.repo_path.path}:{hit.chunk.offset}")
        print(f"   Section: {hit.chunk.section}")
        print(f"   Score: {hit.score:.3f}")
        print(f"   {hit.chunk.text[:200]}{'...' if len(hit.chunk.text) > 200 else ''}")


@app.command()
def stats():
    """Show statistics about your commonplace and search index."""
    from datetime import datetime

    from rich.console import Console
    from rich.table import Table

    config = get_config()

    repo = config.get_repo()
    repo_stats = repo.stats()
    repo_counts = Counter()
    repo_counts.update(config.source(path) for path in repo.note_paths())

    index = config.get_index()
    index_stats = index.stats()
    index_counts = Counter()
    index_counts.update(config.source(path) for path in index.get_indexed_paths())

    print(f"Number of notes: {repo_stats.num_notes:,}")
    print(f"Number of chunks: {index_stats.num_chunks:,}")

    # print(f"  Total size: {humanize.naturalsize(repo_stats.total_size_bytes, binary=True)}")

    # Show date range
    oldest = datetime.fromtimestamp(repo_stats.oldest_timestamp).strftime("%Y-%m-%d")
    print(f"Oldest note: {oldest}")
    newest = datetime.fromtimestamp(repo_stats.newest_timestamp).strftime("%Y-%m-%d")
    print(f"Newest note: {newest}")

    table = Table("Category", "Repo count", "Index count")
    categories = sorted(set(repo_counts) | set(index_counts), key=lambda category: -repo_counts.get(category, 0))
    repo_total = sum(repo_counts.values(), 0)
    index_total = sum(index_counts.values(), 0)

    for category in categories:
        repo_count = repo_counts.get(category, 0)
        index_count = index_counts.get(category, 0)
        table.add_row(
            category,
            f"{repo_count:,} ({repo_count / repo_total:.1%})" if repo_total > 0 else "0",
            f"{index_count:,} ({index_count / index_total:.1%})" if index_total > 0 else "0",
        )

    table.add_section()
    table.add_row("Total", f"{repo_total:,}", f"{index_total:,}")

    console = Console()
    console.print(table)
