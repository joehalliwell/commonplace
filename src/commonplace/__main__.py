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
def index(
    rebuild: bool = typer.Option(False, "--rebuild", help="Rebuild the index from scratch"),
    batch_size: int = typer.Option(100, "--batch-size", help="Number of chunks to embed at once"),
    model: str = typer.Option("3-small", "--model", "-m", help="LLM embedding model ID"),
):
    """Build or rebuild the search index for semantic search."""
    config = get_config()
    repo = Commonplace.open(config.root)
    db_path = config.root / ".commonplace" / "embeddings.db"
    from commonplace._search._commands import index

    index(repo, db_path, rebuild=rebuild, batch_size=batch_size, model_id=model)


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
    db_path = config.root / ".commonplace" / "embeddings.db"

    if not db_path.exists():
        logger.error("Index not found. Run 'commonplace index' first.")
        raise typer.Exit(1)

    from commonplace._search import _commands

    embedder = _commands.LLMEmbedder(model_id=model)
    store = _commands.SQLiteVectorStore(db_path, embedder=embedder)

    try:
        results = store.search(query, limit=limit, method=method)
    except ValueError as e:
        logger.error(str(e))
        raise typer.Exit(1)
    finally:
        store.close()

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
    config = get_config()
    repo = Commonplace.open(config.root)

    print("Repository statistics:")
    repo_stats = repo.stats()
    print(f"  Number of notes: {repo_stats.num_notes:,}")

    from commonplace._search import get_store

    store = get_store(config)
    store_stats = store.stats()
    print("Search index statistics:")
    print(f"  Number of chunks: {store_stats.num_chunks:,}")
    print("  Chunks by embedding model:")
    for model_id, count in store_stats.chunks_by_embedding_model.items():
        print(f"    {model_id}: {count:,}")
