import datetime as dt
import logging
import os
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, Literal, TypeAlias

from cyclopts import App, Parameter
from platformdirs import user_data_dir

from commonplace import _annotate as annotate
from commonplace._fetch._helpers import FetchBlocked
from commonplace._logging import logger
from commonplace._repo import Commonplace
from commonplace._search._types import SearchMethod
from commonplace._types import Note
from commonplace._utils import dump_frontmatter, edit_in_editor, load_frontmatter

DEFAULT_ROOT = Path(user_data_dir("commonplace"))
ENV_PREFIX = "COMMONPLACE"

app = App(
    name="commonplace",
    help="Personal knowledge management tool for the augmented self.",
)

# Type aliases for common parameters.
#
# These must stay `TypeAlias`, not PEP 695 `type` statements: cyclopts reads
# the annotation at runtime and does not unwrap a lazy `TypeAliasType`, so the
# embedded `Parameter(...)` is lost and `--repo` becomes a required CLI
# argument.
Repo: TypeAlias = Annotated[Commonplace, Parameter(parse=False)]  # noqa: UP040
Sources: TypeAlias = Annotated[  # noqa: UP040
    list[str],
    Parameter(
        name=["--source", "-s"],
        help="Filter by source (can be specified multiple times)",
        negative="",
        show_default=False,
    ),
]
Index: TypeAlias = Annotated[  # noqa: UP040
    bool | None,
    Parameter(help="Index what this run commits (default: from config)"),
]


@app.meta.default
def _launch(
    *tokens: Annotated[str, Parameter(show=False, allow_leading_hyphen=True)],
    verbose: Annotated[
        bool,
        Parameter(
            name=["-v", "--verbose"],
            help="Provide more detailed logging; --no-verbose overrides the environment.",
            env_var=f"{ENV_PREFIX}_VERBOSE",
        ),
    ] = False,
    root: Annotated[
        Path,
        Parameter(name=["--root"], help="Path to the commonplace root directory.", env_var=f"{ENV_PREFIX}_ROOT"),
    ] = Path(os.getenv(f"{ENV_PREFIX}_ROOT", DEFAULT_ROOT)),  # noqa: B008 - cyclopts renders the default in --help
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

    except FetchBlocked as e:
        # Not a bug: the message tells the user what to do, and a traceback
        # would bury it.
        logger.error(str(e))
        raise SystemExit(1) from e

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


@contextmanager
def _indexing(repo: Commonplace, index: bool | None) -> Iterator[None]:
    """Index once what the body commits, even if it fails part way, when `index` or else the config says to."""
    before = repo.head()
    try:
        yield
    finally:
        # Opening the index loads the embedding model, so a command that committed nothing doesn't.
        if (repo.config.auto_index if index is None else index) and repo.head() != before:
            from commonplace._search._commands import index as index_notes

            logger.info("Indexing committed notes")
            index_notes(repo, rebuild=False)


################################################################################
# Commands that create notes
################################################################################
CREATING_SECTION = "Creating notes"


@app.command(name="import", alias="i", group=CREATING_SECTION)
def import_(
    path: Path,
    *,
    index: Index = None,
    repo: Repo,
) -> None:
    """Import AI conversation exports (Claude ZIP, Gemini Takeout) into your commonplace."""

    from commonplace._import._commands import import_

    with _indexing(repo, index):
        import_(path, repo, user=repo.config.user)


@app.command(alias="f", group=CREATING_SECTION)
def fetch(
    *,
    full: Annotated[bool, Parameter(help="Ignore the cursor and fetch everything the remote has.")] = False,
    index: Index = None,
    sources: Sources = [],  # noqa: B006 - cyclopts' idiom for a repeatable flag; never mutated
    repo: Repo,
) -> None:
    """Fetch new conversations directly from each source and import them."""

    from commonplace._fetch._commands import fetch

    with _indexing(repo, index):
        fetch(repo, names=sources or None, all_=full)


@app.command(alias="j", group=CREATING_SECTION)
def journal(
    date: Annotated[str | None, Parameter(help="Date for the journal entry (YYYY-MM-DD)")] = None,
    *,
    index: Index = None,
    repo: Repo,
) -> None:
    """Create or edit a daily journal entry."""

    # Journals are keyed by the user's local calendar day, not by instant, so
    # both of these are deliberately naive. Using UTC here would file an entry
    # written just after midnight under the previous day.
    if date is None:
        day = dt.datetime.now()  # noqa: DTZ005
    else:
        try:
            day = dt.datetime.strptime(date, "%Y-%m-%d")  # noqa: DTZ007
        except ValueError as e:
            logger.error(f"Invalid date format '{date}'. Use YYYY-MM-DD (e.g., 2025-10-11)")
            raise SystemExit(1) from e

    journal_path = repo.root / "journal" / day.strftime("%Y/%m/%Y-%m-%d.md")
    default_content = f"# {day.strftime('%A, %B %d, %Y')}\n\n## Tasks\n\n## Notes\n\n"

    # Ensure parent directory exists
    journal_path.parent.mkdir(parents=True, exist_ok=True)

    path = journal_path.relative_to(repo.root)

    # Load existing content or use default (but don't create file yet)
    note = repo.get(path) if journal_path.exists() else Note(path, default_content)
    original_content = dump_frontmatter(note.metadata, note.body)

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
    metadata, body = load_frontmatter(edited_content)
    repo.put(Note(path, body, metadata))
    logger.info(f"Saved journal entry to {journal_path.relative_to(repo.root)}")

    # Commit the journal entry
    with _indexing(repo, index):
        repo.commit(f"Update journal entry for {day.strftime('%Y-%m-%d')}")


################################################################################
# Commands that analyze notes
################################################################################
ANALYZING_SECTION = "Analyzing"


@app.command(name="search", alias="s", group=ANALYZING_SECTION)
def search(
    *query: str,
    limit: Annotated[int, Parameter(name=["--limit", "-n"], help="Maximum number of results")] = 10,
    method: Annotated[SearchMethod, Parameter(help="Search method")] = SearchMethod.HYBRID,
    deleted: Annotated[bool, Parameter(help="Include notes that have been deleted since indexing")] = False,
    hidden: Annotated[bool, Parameter(help="Include notes tagged hidden")] = False,
    repo: Repo,
) -> None:
    """Search for semantically similar content in your commonplace."""

    from commonplace._search._commands import open_index

    results = open_index(repo).search(
        " ".join(query), limit=limit, method=method, include_deleted=deleted, include_hidden=hidden
    )

    if not results:
        logger.info("No results found")
        return

    # Display results
    for i, hit in enumerate(results, 1):
        print(f"\n{i}. {hit.chunk.version.path}:{hit.chunk.offset}")
        print(f"   Section: {hit.chunk.section}")
        print(f"   Score: {hit.score:.3f}")
        print(f"   {hit.chunk.text[:200]}{'...' if len(hit.chunk.text) > 200 else ''}")


@app.command(group=ANALYZING_SECTION)
def ls(
    folder: Annotated[Path, Parameter(help="Folder to list, relative to the commonplace root")] = Path("."),
    *,
    fields: Annotated[
        list[str],
        Parameter(name=["--field", "-f"], help="Also show this frontmatter key", negative="", show_default=False),
    ] = [],  # noqa: B006 - cyclopts' idiom for a repeatable flag; never mutated
    hidden: Annotated[bool, Parameter(help="Include notes tagged hidden")] = False,
    repo: Repo,
) -> None:
    """List a folder's notes with their titles and descriptions, as an OKF index."""
    from commonplace._listing import listing

    try:
        print(listing(repo, folder, fields, hidden), end="")
    except ValueError as e:
        logger.error(str(e))
        raise SystemExit(1) from e


################################################################################
# Annotating commands
################################################################################

ANNOTATING_SECTION = "Annotating"

NoteSpec: TypeAlias = Annotated[  # noqa: UP040
    str, Parameter(help="A note, named as a wikilink would: 'ideas' or '/notes/ideas'; a * makes it a glob")
]


@app.command(group=ANALYZING_SECTION)
def show(
    spec: NoteSpec,
    *,
    only: Annotated[
        list[str],
        Parameter(help="Show just this section: tags, links, commentary or index", negative=""),
    ] = [],  # noqa: B006 - cyclopts' idiom for a repeatable flag; never mutated
    as_json: Annotated[bool, Parameter(name="--json", help="The record as JSON rather than YAML")] = False,
    hidden: Annotated[bool, Parameter(help="Include links to and from notes tagged hidden")] = False,
    repo: Repo,
) -> None:
    """Everything known about a note, as YAML: tags, links both ways, commentary, index."""
    import json

    from commonplace._show import SECTIONS, render, select
    from commonplace._show import show as gather

    unknown = set(only) - set(SECTIONS)
    try:
        if unknown:
            raise ValueError(f"No section {', '.join(sorted(unknown))}; there are {', '.join(SECTIONS)}")
        shown = gather(repo, spec, hidden)
    except ValueError as e:
        logger.error(str(e))
        raise SystemExit(1) from e
    print(
        json.dumps(select(shown, only), ensure_ascii=False) if as_json else render(shown, only),
        end="\n" if as_json else "",
    )


@app.command(group=ANALYZING_SECTION)
def resolve(spec: NoteSpec, *, repo: Repo) -> None:
    """Print the path of the note a name refers to, one per line for a glob: $EDITOR $(commonplace resolve ideas)."""

    try:
        notes = repo.files.resolve(spec)
    except ValueError as e:
        logger.error(str(e))
        raise SystemExit(1) from e
    for note in notes:
        print(repo.root / note)


@app.command(group=ANNOTATING_SECTION)
def tag(spec: NoteSpec, *tags: str, repo: Repo) -> None:
    """Tag notes, in their marginalia; `show <note> --only tags` shows a note's tags."""
    try:
        if not tags:
            raise ValueError("Name a tag to add; `commonplace show <note> --only tags` shows a note's tags")
        annotate.tag(repo, spec, list(tags))
    except ValueError as e:  # No tag, an unresolved spec, or marginalia newer than this release
        logger.error(str(e))
        raise SystemExit(1) from e


@app.command(group=ANNOTATING_SECTION)
def untag(spec: NoteSpec, *tags: str, repo: Repo) -> None:
    """Remove tags from notes' marginalia."""
    try:
        annotate.untag(repo, spec, list(tags))
    except ValueError as e:
        logger.error(str(e))
        raise SystemExit(1) from e


@app.command(group=ANNOTATING_SECTION)
def link(
    note: Annotated[str, Parameter(help="The note the link is about, named as a wikilink would")],
    target: Annotated[
        str, Parameter(help="Where it points: a note, or a span in one ('note#Heading', 'note#\"phrase\"')")
    ],
    *why: str,
    repo: Repo,
) -> None:
    """Link one note to another, in the first note's marginalia; the rest of the line says why."""
    try:
        annotate.link(repo, note, target, " ".join(why))
    except ValueError as e:
        logger.error(str(e))
        raise SystemExit(1) from e


@app.command(group=ANNOTATING_SECTION)
def unlink(note: NoteSpec, target: NoteSpec, *, repo: Repo) -> None:
    """Remove a note's links to a target from its marginalia."""
    try:
        annotate.unlink(repo, note, target)
    except ValueError as e:
        logger.error(str(e))
        raise SystemExit(1) from e


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
    _args = ["-C", str(repo.root), *args]

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
    logger.info("")
    logger.info("To enable Claude Code plugins, run in Claude Code:")
    logger.info("  /plugin marketplace add joehalliwell/commonplace")


@app.command(group=SYSTEM_SECTION)
def index(
    *,
    rebuild: Annotated[bool, Parameter(help="Rebuild the index from scratch")] = False,
    prune: Annotated[bool, Parameter(help="Drop chunks for deleted or edited notes")] = True,
    repo: Repo,
) -> None:
    """Build or rebuild the search index for semantic search."""

    from commonplace._search._commands import index

    index(repo, rebuild=rebuild, prune=prune)


@app.command(group=SYSTEM_SECTION)
def sync(
    *,
    auto_commit: Annotated[bool, Parameter(help="Auto-commit uncommitted changes")] = True,
    branch: Annotated[str | None, Parameter(help="Branch name (default: current)")] = None,
    remote: Annotated[str, Parameter(help="Remote name")] = "origin",
    strategy: Annotated[Literal["rebase", "merge"], Parameter(help="Sync strategy")] = "rebase",
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
    scaffold: Annotated[bool, Parameter(help="Restore missing scaffolding and report template drift.")] = True,
    links: Annotated[bool, Parameter(help="Report broken links, in notes and their marginalia.")] = True,
    marginalia: Annotated[
        bool,
        Parameter(help="Re-attach marginalia to moved notes; report marginalia whose note is gone."),
    ] = True,
    render: Annotated[
        bool, Parameter(help="Re-render chats from the stored archives, newest capture winning; takes minutes.")
    ] = False,
    check: Annotated[bool, Parameter(help="Report what would change without writing.")] = False,
    repo: Repo,
) -> None:
    """Check and fix the repository, one operation at a time: each flag selects one."""
    from commonplace._doctor import doctor

    doctor(repo, check=check, scaffold=scaffold, links=links, marginalia=marginalia, render=render)


@app.command(group=SYSTEM_SECTION)
def config(
    key: Annotated[str | None, Parameter(help="Print only this setting's value")] = None,
    *,
    repo: Repo,
) -> None:
    """Print the settings in effect, after environment and config files are merged."""
    import tomli_w

    settings = repo.config.model_dump(mode="json")
    if key is None:
        print(tomli_w.dumps(settings), end="")
    elif isinstance(value := settings.get(key), str):
        print(value)  # Unquoted, so scripts can use it directly
    elif key in settings:
        print(tomli_w.dumps({key: value}).removeprefix(f"{key} = "), end="")
    else:
        logger.error(f"Unknown setting '{key}'. Settings: {', '.join(settings)}")
        raise SystemExit(1)


@app.command(group=SYSTEM_SECTION)
def stats(
    *folders: Annotated[str, Parameter(help="Only these folders, relative to the root (e.g. chats/claude journal)")],
    all_time: Annotated[bool, Parameter(name=["--all"], help="Show full history (default: last 52 weeks)")] = False,
    repo: Repo,
) -> None:
    """Show statistics about your commonplace and search index."""

    from commonplace._stats import generate_stats, source

    try:
        heatmap_output, table_output = generate_stats(
            repo,
            sources=list(folders) or None,
            all_time=all_time,
        )

        # Display the outputs (captured strings already have ANSI formatting)
        if heatmap_output:
            print(heatmap_output, end="")
        print(table_output, end="")

    except ValueError as e:
        logger.error(str(e))
        # Show available sources
        available_sources = sorted({source(path) for path in repo.note_paths()})
        logger.info(f"Available sources: {', '.join(available_sources)}")
        return


if __name__ == "__main__":
    app.meta()
