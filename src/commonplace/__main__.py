import datetime as dt
import logging
import subprocess
from collections import Counter
from pathlib import Path
from typing import Optional

import typer
from rich.logging import RichHandler

from commonplace import get_config, logger
from commonplace._repo import Commonplace
from commonplace._search._types import SearchMethod
from commonplace._types import Note
from commonplace._utils import edit_in_editor

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

    from rich.console import Console
    from rich.progress import track
    from rich.table import Table

    config = get_config()

    # Collate the stats
    repo = config.get_repo()
    repo_counts = Counter()
    repo_counts.update(
        config.source(path) for path in track(repo.note_paths(), description="Scanning repo", transient=True)
    )

    index = config.get_index()
    index_chunks_by_source = Counter()
    for stat in track(index.stats(), description="Scanning index", transient=True):
        index_chunks_by_source.update({config.source(stat.repo_path): stat.num_chunks})

    sources = sorted(
        set(repo_counts) | set(index_chunks_by_source),
        key=lambda category: -repo_counts.get(category, 0),
    )

    # Display them
    table = Table("Source", "Files", "Indexed chunks")
    repo_total = sum(repo_counts.values(), 0)
    index_total = sum(index_chunks_by_source.values(), 0)

    def make_percentage(val, total):
        return f"{val:<6,} [dim]{val / total:>6.1%}[/]" if total > 0 else "0"

    # Add a row for each source
    for source in sources:
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

    console = Console()
    console.print(table)


@app.command()
def journal(date_str: Optional[str] = typer.Argument(None, help="Date for the journal entry (YYYY-MM-DD)")):
    """Create or edit a daily journal entry."""
    config = get_config()
    repo = config.get_repo()

    if date_str is None:
        date = dt.datetime.now()
    else:
        try:
            date = dt.datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError as e:
            logger.error(f"Invalid date format '{date_str}'. Use YYYY-MM-DD (e.g., 2025-10-11)")
            raise typer.Exit(1) from e

    journal_path = repo.root / "journal" / date.strftime("%Y/%m/%Y-%m-%d.md")
    default_content = f"# {date.strftime('%A, %B %d, %Y')}\n\n## Tasks\n\n## Notes\n\n"

    # Ensure parent directory exists
    journal_path.parent.mkdir(parents=True, exist_ok=True)

    repo_path = repo.make_repo_path(journal_path)

    # Load existing content or use default (but don't create file yet)
    if journal_path.exists():
        note = repo.get_note(repo_path)
        original_content = note.content
    else:
        original_content = default_content

    # Open in editor
    try:
        edited_content = edit_in_editor(original_content, config.editor)
    except subprocess.CalledProcessError as e:
        logger.error(f"Editor exited with error code {e.returncode}")
        raise typer.Exit(1) from e
    except FileNotFoundError as e:
        logger.error(f"Editor '{config.editor}' not found. Set COMMONPLACE_EDITOR environment variable or config.")
        raise typer.Exit(1) from e

    # If no changes, we're done
    if edited_content is None:
        return

    # Save the edited content (creates file if it doesn't exist)
    note = Note(repo_path=repo_path, content=edited_content)
    repo.save(note)
    logger.info(f"Saved journal entry to {journal_path.relative_to(repo.root)}")
