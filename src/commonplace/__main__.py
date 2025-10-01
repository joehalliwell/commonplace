import logging
from pathlib import Path

import typer
from rich.logging import RichHandler

from commonplace import _import, _search, get_config, logger
from commonplace._repo import Commonplace

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
    _import.import_(path, repo, user=config.user, prefix="chats")


@app.command()
def init():
    """Initialize a commonplace working directory."""
    config = get_config()
    Commonplace.init(config.root)


@app.command()
def index(
    rebuild: bool = typer.Option(False, "--rebuild", help="Rebuild the index from scratch"),
    batch_size: int = typer.Option(100, "--batch-size", help="Number of chunks to embed at once"),
):
    """Build or rebuild the search index for semantic search."""
    config = get_config()
    repo = Commonplace.open(config.root)
    db_path = config.root / ".commonplace" / "embeddings.db"

    _search.index(repo, db_path, rebuild=rebuild, batch_size=batch_size)


@app.command()
def search(
    query: str,
    limit: int = typer.Option(10, "--limit", "-n", help="Maximum number of results"),
    method: str = typer.Option("hybrid", "--method", "-m", help="Search method: semantic, fts, or hybrid"),
):
    """Search for semantically similar content in your commonplace."""
    config = get_config()
    db_path = config.root / ".commonplace" / "embeddings.db"

    try:
        results = _search.search(db_path, query, limit=limit, method=method)
    except FileNotFoundError as e:
        logger.error(str(e))
        raise typer.Exit(1)
    except ValueError as e:
        logger.error(str(e))
        raise typer.Exit(1)

    if not results:
        logger.info("No results found")
        return

    # Display results
    for i, hit in enumerate(results, 1):
        print(f"\n{i}. {hit.chunk.path}:{hit.chunk.offset}")
        print(f"   Section: {hit.chunk.section}")
        print(f"   Score: {hit.score:.3f}")
        print(f"   {hit.chunk.text[:200]}{'...' if len(hit.chunk.text) > 200 else ''}")
