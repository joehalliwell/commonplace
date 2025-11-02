import datetime as dt
import logging
import subprocess
from collections import Counter
from pathlib import Path
from typing import Annotated, Optional

from cyclopts import Parameter, App
from rich.logging import RichHandler

from commonplace import get_config, logger
from commonplace._repo import Commonplace
from commonplace._search._types import SearchMethod
from commonplace._types import Note
from commonplace._utils import edit_in_editor

app = App(help="Commonplace: Personal knowledge management")

CREATING_SECTION = "Creating notes"
ANALYZING_SECTION = "Analyzing"
SYSTEM_SECTION = "System"


@app.meta.default
def launch(
    *tokens: Annotated[str, Parameter(show=False, allow_leading_hyphen=True)],
    root: Annotated[
        Optional[Path],
        Parameter(name=["--root"], help="Path to the commonplace root directory."),
    ] = None,
    verbose: Annotated[
        bool,
        Parameter(name=["-v", "--verbose"], help="Provide more detailed logging.", negative=[]),
    ] = False,
):
    """Set up common parameters for all commands."""
    # Setup logging before anything else!
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.addHandler(RichHandler())
    config = get_config()

    if root is not None:
        logger.warning(f"Overriding root: {config.root}")
        config.root = root

    app(tokens)


################################################################################
# Commands that create notes
################################################################################


@app.command(name="import", alias="i", group=CREATING_SECTION)
def import_(path: Path):
    """Import AI conversation exports (Claude ZIP, Gemini Takeout) into your commonplace."""
    config = get_config()
    repo = Commonplace.open(config.root)

    from commonplace._import._commands import import_

    import_(path, repo, user=config.user, prefix="chats")


@app.command(alias="j", group=CREATING_SECTION)
def journal(
    date_str: Annotated[Optional[str], Parameter(help="Date for the journal entry (YYYY-MM-DD)")] = None,
):
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
            raise SystemExit(1) from e

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
        raise SystemExit(1) from e
    except FileNotFoundError as e:
        logger.error(f"Editor '{config.editor}' not found. Set COMMONPLACE_EDITOR environment variable or config.")
        raise SystemExit(1) from e

    # If no changes, we're done
    if edited_content is None:
        return

    # Save the edited content (creates file if it doesn't exist)
    note = Note(repo_path=repo_path, content=edited_content)
    repo.save(note)
    logger.info(f"Saved journal entry to {journal_path.relative_to(repo.root)}")


################################################################################
# Commands that analyze notes
################################################################################


@app.command(name="search", alias="s", group=ANALYZING_SECTION)
def search(
    query: str,
    /,
    limit: Annotated[int, Parameter(name=["--limit", "-n"], help="Maximum number of results")] = 10,
    method: Annotated[
        SearchMethod, Parameter(help="Search method: semantic, keyword, or hybrid")
    ] = SearchMethod.HYBRID,
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


################################################################################
# System commands
################################################################################


@app.command(group=SYSTEM_SECTION)
def git(
    args: list[str],
):
    """Execute a git command in the commonplace repository. Requires git to be
    installed and on PATH."""
    import os
    import shlex

    config = get_config()

    cmd = "git"
    args = [f"--git-dir={config.root / '.git'}", f"--work-tree={config.root}", *args]

    logger.info(f"Executing command: {cmd} {shlex.join(args)}")
    os.execlp(cmd, cmd, *args)


@app.command(group=SYSTEM_SECTION)
def init():
    """Initialize a commonplace working directory."""
    config = get_config()
    Commonplace.init(config.root)


@app.command(group=SYSTEM_SECTION)
def index(
    rebuild: Annotated[bool, Parameter(help="Rebuild the index from scratch")] = False,
):
    """Build or rebuild the search index for semantic search."""
    config = get_config()

    from commonplace._search._commands import index

    index(config.get_repo(), config.get_index(), rebuild=rebuild)


@app.command(group=SYSTEM_SECTION)
def sync(
    remote: Annotated[str, Parameter(help="Remote name")] = "origin",
    branch: Annotated[Optional[str], Parameter(help="Branch name (default: current)")] = None,
    strategy: Annotated[str, Parameter(help="Sync strategy: rebase or merge")] = "rebase",
    auto_commit: Annotated[bool, Parameter(help="Auto-commit uncommitted changes")] = True,
):
    """Synchronize with remote repository (add changes, pull, push)."""
    config = get_config()
    repo = config.get_repo()

    try:
        repo.sync(
            remote_name=remote,
            branch=branch,
            strategy=strategy,
            auto_commit=auto_commit,
        )
    except ValueError as e:
        logger.error(f"Sync failed: {e}")
        raise SystemExit(1) from e


@app.command(group=SYSTEM_SECTION)
def stats():
    """Show statistics about your commonplace and search index."""

    from rich.console import Console
    from rich.progress import track
    from rich.table import Table

    config = get_config()

    # Collate the stats
    repo = config.get_repo()
    repo_counts: Counter[str] = Counter()
    repo_counts.update(
        config.source(path) for path in track(repo.note_paths(), description="Scanning repo", transient=True)
    )

    index = config.get_index()
    index_chunks_by_source: Counter[str] = Counter()
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


def main():
    app.meta()
