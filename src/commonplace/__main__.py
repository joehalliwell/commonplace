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

    index(config.get_repo(), config.get_store(), rebuild=rebuild)


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

    store = config.get_store()
    results = store.search(query, limit=limit, method=method)

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

    import humanize

    config = get_config()
    repo = config.get_repo()

    print("Repository statistics:")
    repo_stats = repo.stats()
    print(f"  Number of notes: {repo_stats.num_notes:,}")
    print(f"  Total size: {humanize.naturalsize(repo_stats.total_size_bytes, binary=True)}")

    # Show providers
    if repo_stats.num_per_type:
        print("  Notes by type:")
        for provider, count in sorted(repo_stats.num_per_type.items()):
            print(f"    {provider}: {count:,}")

    # Show date range
    if repo_stats.oldest_timestamp > 0:
        oldest = datetime.fromtimestamp(repo_stats.oldest_timestamp).strftime("%Y-%m-%d")
        newest = datetime.fromtimestamp(repo_stats.newest_timestamp).strftime("%Y-%m-%d")
        print(f"  Date range: {oldest} to {newest}")

    store = config.get_store()
    store_stats = store.stats()
    print("\nSearch index statistics:")
    print(f"  Number of notes: {store_stats.num_docs:,}")
    print(f"  Number of chunks: {store_stats.num_chunks:,}")
    print("  Chunks by embedding model:")
    for model_id, count in store_stats.chunks_by_embedding_model.items():
        print(f"    {model_id}: {count:,}")
