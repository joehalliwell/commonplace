import logging
from pathlib import Path

import typer
from rich.logging import RichHandler

from commonplace import _import, get_config, logger
from commonplace._repo import Commonplace
from commonplace._search._chunker import MarkdownChunker
from commonplace._search._embedder import SentenceTransformersEmbedder
from commonplace._search._store import SQLiteVectorStore
from commonplace._utils import progress_track

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

    # Set up components
    db_path = config.root / ".commonplace" / "embeddings.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    store = SQLiteVectorStore(db_path)
    chunker = MarkdownChunker()
    embedder = SentenceTransformersEmbedder()

    if rebuild:
        logger.info("Clearing existing index")
        store.clear()

    # Collect all notes and chunks
    notes = list(repo.notes())
    logger.info(f"Chunking {len(notes)} notes")

    all_chunks = []
    for note in progress_track(notes, "Chunking notes"):
        chunks = list(chunker.chunk(note))
        all_chunks.extend(chunks)

    logger.info(f"Embedding {len(all_chunks)} chunks in batches of {batch_size}")

    # Process chunks in batches
    num_batches = (len(all_chunks) + batch_size - 1) // batch_size
    for i in progress_track(range(0, len(all_chunks), batch_size), "Embedding chunks", total=num_batches):
        batch = all_chunks[i : i + batch_size]
        texts = [chunk.text for chunk in batch]
        embeddings = embedder.embed_batch(texts)

        # Store each chunk with its embedding
        for chunk, embedding in zip(batch, embeddings):
            store.add(chunk, embedding)

    store.close()
    logger.info("Indexing complete")


@app.command()
def search(
    query: str,
    limit: int = typer.Option(10, "--limit", "-n", help="Maximum number of results"),
    method: str = typer.Option("hybrid", "--method", "-m", help="Search method: semantic, fts, or hybrid"),
):
    """Search for semantically similar content in your commonplace."""
    config = get_config()

    # Set up components
    db_path = config.root / ".commonplace" / "embeddings.db"
    if not db_path.exists():
        logger.error("Index not found. Run 'commonplace index' first.")
        raise typer.Exit(1)

    store = SQLiteVectorStore(db_path)

    # Search based on method
    if method == "fts":
        results = store.search_fts(query, limit=limit)
    elif method == "semantic":
        embedder = SentenceTransformersEmbedder()
        query_embedding = embedder.embed(query)
        results = store.search(query_embedding, limit=limit)
    elif method == "hybrid":
        embedder = SentenceTransformersEmbedder()
        query_embedding = embedder.embed(query)
        results = store.search_hybrid(query, query_embedding, limit=limit)
    else:
        logger.error(f"Unknown search method: {method}")
        raise typer.Exit(1)

    if not results:
        logger.info("No results found")
        store.close()
        return

    # Display results
    for i, hit in enumerate(results, 1):
        print(f"\n{i}. {hit.chunk.path}:{hit.chunk.offset}")
        print(f"   Section: {hit.chunk.section}")
        print(f"   Score: {hit.score:.3f}")
        print(f"   {hit.chunk.text[:200]}{'...' if len(hit.chunk.text) > 200 else ''}")

    store.close()
