import datetime as dt
import logging
import os
import subprocess
from pathlib import Path
from typing import Annotated, Optional, TypeAlias

from cyclopts import App, Parameter
from platformdirs import user_data_dir

from commonplace._logging import logger
from commonplace._repo import Commonplace
from commonplace._search._types import SearchMethod
from commonplace._types import Note
from commonplace._utils import edit_in_editor

DEFAULT_ROOT = Path(user_data_dir("commonplace"))
ENV_PREFIX = "COMMONPLACE"

app = App(
    name="commonplace",
    help="Personal knowledge management tool for the augmented self.",
)

# Type aliases for common parameters
Repo: TypeAlias = Annotated[Commonplace, Parameter(parse=False)]
Sources: TypeAlias = Annotated[
    list[str],
    Parameter(
        name=["--source", "-s"],
        help="Filter by source (can be specified multiple times)",
        negative="",
        show_default=False,
    ),
]


@app.meta.default
def _launch(
    *tokens: Annotated[str, Parameter(show=False, allow_leading_hyphen=True)],
    verbose: Annotated[
        bool,
        Parameter(
            name=["-v", "--verbose"],
            help="Provide more detailed logging.",
            negative=[],
            env_var=f"{ENV_PREFIX}_VERBOSE",
        ),
    ] = False,
    root: Annotated[
        Path,
        Parameter(name=["--root"], help="Path to the commonplace root directory.", env_var=f"{ENV_PREFIX}_ROOT"),
    ] = Path(os.getenv("COMMONPLACE_ROOT", DEFAULT_ROOT)),
) -> None:
    """Set up common parameters for all commands."""

    # Setup logging before doing anything else!
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)

    try:
        extras = {}
        command, bound, ignored = app.parse_args(tokens)
        if "repo" in ignored:  # Inject repo if command needs it
            extras["repo"] = _open_repo(root)
        return command(*bound.args, **bound.kwargs, **extras)

    except Exception as e:
        logger.exception(f"Error executing command: {e}")
        raise SystemExit(1) from e


def _open_repo(root: Path) -> Commonplace:
    """Try to open a commonplace repository at the given root path. Exit on
    failure with a helpful message.

    TODO: Make messages more helpful.
    """
    try:
        repo = Commonplace.open(root)
    except Exception as e:
        logger.error(f"Failed to open commonplace repository at {root}: {e}")
        raise SystemExit(1) from e
    return repo


################################################################################
# Commands that create notes
################################################################################
CREATING_SECTION = "Creating notes"


@app.command(name="import", alias="i", group=CREATING_SECTION)
def import_(
    path: Path,
    index: Annotated[
        Optional[bool],
        Parameter(help="Index notes after commit (default: from config)"),
    ] = None,
    *,
    repo: Repo,
) -> None:
    """Import AI conversation exports (Claude ZIP, Gemini Takeout) into your commonplace."""

    from commonplace._import._commands import import_

    import_(path, repo, user=repo.config.user, prefix="chats", auto_index=index)


@app.command(alias="j", group=CREATING_SECTION)
def journal(
    date_str: Annotated[Optional[str], Parameter(help="Date for the journal entry (YYYY-MM-DD)")] = None,
    index: Annotated[
        Optional[bool],
        Parameter(help="Index notes after commit (default: from config)"),
    ] = None,
    *,
    repo: Repo,
) -> None:
    """Create or edit a daily journal entry."""

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
        edited_content = edit_in_editor(original_content, repo.config.editor)
    except subprocess.CalledProcessError as e:
        logger.error(f"Editor exited with error code {e.returncode}")
        raise SystemExit(1) from e
    except FileNotFoundError as e:
        logger.error(f"Editor '{repo.config.editor}' not found. Set COMMONPLACE_EDITOR environment variable or config.")
        raise SystemExit(1) from e

    # If no changes, we're done
    if edited_content is None:
        return

    # Save the edited content (creates file if it doesn't exist)
    note = Note(repo_path=repo_path, content=edited_content)
    repo.save(note)
    logger.info(f"Saved journal entry to {journal_path.relative_to(repo.root)}")

    # Commit the journal entry
    repo.commit(f"Update journal entry for {date.strftime('%Y-%m-%d')}", auto_index=index)


################################################################################
# Commands that analyze notes
################################################################################
ANALYZING_SECTION = "Analyzing"


@app.command(name="search", alias="s", group=ANALYZING_SECTION)
def search(
    *query: str,
    limit: Annotated[int, Parameter(name=["--limit", "-n"], help="Maximum number of results")] = 10,
    method: Annotated[SearchMethod, Parameter(help="Search method")] = SearchMethod.HYBRID,
    repo: Repo,
) -> None:
    """Search for semantically similar content in your commonplace."""

    results = repo.index.search(" ".join(query), limit=limit, method=method)

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

SYSTEM_SECTION = "System"


@app.command(
    group=SYSTEM_SECTION,
)
def git(
    *args: Annotated[str, Parameter(allow_leading_hyphen=True)],
    repo: Repo,
) -> None:
    """Execute a git command in the commonplace repository. Requires git to be
    installed and on PATH."""
    import shlex

    cmd = "git"
    _args = [f"--git-dir={repo.root / '.git'}", f"--work-tree={repo.root}", *args]

    logger.info(f"Executing command: {cmd} {shlex.join(_args)}")
    os.execlp(cmd, cmd, *_args)


@app.meta.command(group=SYSTEM_SECTION)
def init(root: Path) -> None:
    """Initialize a commonplace working directory."""
    Commonplace.init(root)
    if root != DEFAULT_ROOT:
        logger.warning(
            f"Initialized commonplace at {root}. To use it, run commands with --root {root} or set COMMONPLACE_ROOT."
        )


@app.command(group=SYSTEM_SECTION)
def index(
    rebuild: Annotated[bool, Parameter(help="Rebuild the index from scratch")] = False,
    *,
    repo: Repo,
) -> None:
    """Build or rebuild the search index for semantic search."""

    from commonplace._search._commands import index

    index(repo, rebuild=rebuild)


@app.command(group=SYSTEM_SECTION)
def sync(
    remote: Annotated[str, Parameter(help="Remote name")] = "origin",
    branch: Annotated[Optional[str], Parameter(help="Branch name (default: current)")] = None,
    strategy: Annotated[str, Parameter(help="Sync strategy: rebase or merge")] = "rebase",
    auto_commit: Annotated[bool, Parameter(help="Auto-commit uncommitted changes")] = True,
    *,
    repo: Repo,
) -> None:
    """Synchronize with remote repository (add changes, pull, push)."""

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
def doctor(
    *,
    repo: Repo,
) -> None:
    """Check and fix repository scaffolding (settings, LFS config, etc.)."""
    actions = repo.doctor()
    if actions:
        for action in actions:
            logger.info(action)
    else:
        logger.info("Everything looks good")


@app.command(group=SYSTEM_SECTION)
def stats(
    *,
    sources: Sources = [],
    all_time: Annotated[
        bool,
        Parameter(name=["--all"], help="Show full history (default: last 52 weeks)", negative=""),
    ] = False,
    repo: Repo,
) -> None:
    """Show statistics about your commonplace and search index."""

    from commonplace._stats import generate_stats

    try:
        heatmap_output, table_output = generate_stats(
            repo,
            sources=sources if sources else None,
            all_time=all_time,
        )

        # Display the outputs (captured strings already have ANSI formatting)
        if heatmap_output:
            print(heatmap_output, end="")
        print(table_output, end="")

    except ValueError as e:
        logger.error(str(e))
        # Show available sources
        all_note_paths = list(repo.note_paths())
        available_sources = sorted(set(repo.source(path) for path in all_note_paths))
        logger.info(f"Available sources: {', '.join(available_sources)}")
        return


if __name__ == "__main__":
    app.meta()
