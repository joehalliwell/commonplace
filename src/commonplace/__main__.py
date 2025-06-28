import logging
from pathlib import Path

import typer
from rich.logging import RichHandler
from rich.progress import track

from commonplace import get_config, logger
from commonplace._claude import ClaudeImporter
from commonplace._gemini import GeminiImporter
from commonplace._git import GitRepo
from commonplace._journal import JournalGenerator
from commonplace._llm import get_model
from commonplace._store import ActivityLogDirectoryStore, MarkdownSerializer

app = typer.Typer(
    help="Commonplace: Personal knowledge management for AI conversations",
    pretty_exceptions_enable=False,
)


@app.callback()
def _setup_logging(verbose: bool = typer.Option(False, "--verbose", "-v")):
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.addHandler(RichHandler())


@app.command(name="import")
def import_(path: Path):
    """Import AI conversation exports (Claude ZIP, Gemini Takeout) into your commonplace."""

    try:
        if not path.exists():
            logger.error(f"The file {path} does not exist.")
            raise typer.Exit(code=1)
        if not path.is_file():
            logger.error(f"The path {path} is not a file.")
            raise typer.Exit(code=1)
    except PermissionError:
        logger.exception(f"Permission denied accessing {path}")
        raise typer.Exit(code=1)
    except OSError:
        logger.exception(f"Error accessing {path}")
        raise typer.Exit(code=1)

    importers = [GeminiImporter(), ClaudeImporter()]
    importer = next((imp for imp in importers if imp.can_import(path)), None)
    if importer is None:
        logger.error(f"The file {path} is not supported by any available importer.")
        raise typer.Exit(code=1)
    logger.info(f"Using {importer.source} importer for {path}.")

    try:
        logs = importer.import_(path)
        logger.info(f"Imported {len(logs)} activity logs from {path}.")
    except Exception:
        logger.exception(f"Failed to import from {path}")
        raise typer.Exit(code=1)

    try:
        config = get_config()
        store = ActivityLogDirectoryStore(
            root=config.root / "chats",
            serializer=MarkdownSerializer(human="Joe", assistant=importer.source.title()),
        )

        # Track imported files for git commit
        imported_files = []
        for log in track(logs):
            file_path = store.path(log.source, log.created, log.title)
            store.store(log)
            imported_files.append(str(file_path))

        logger.info(f"Successfully stored {len(logs)} logs")

        # Auto-commit only the imported files if git repo exists
        git_repo = GitRepo(config.root)
        if git_repo.is_available() and imported_files:
            commit_message = (
                f"Import {len(logs)} {importer.source} conversation{'s' if len(logs) != 1 else ''} from {path.name}"
            )
            if git_repo.commit_changes(commit_message, files=imported_files):
                logger.debug("Auto-committed imported conversations")

    except Exception:
        logger.exception("Failed to store logs")
        raise typer.Exit(code=1)


@app.command()
def init():
    """Initialize the commonplace directory as a git repository."""
    config = get_config()
    git_repo = GitRepo(config.root)

    if git_repo.init_repo():
        logger.info("Successfully initialized commonplace git repository")
    else:
        logger.error("Failed to initialize git repository")
        raise typer.Exit(code=1)


@app.command()
def journal(
    days: int = typer.Option(7, "--days", "-d", help="Number of days to analyze"),
    model_name: str = typer.Option("gemini/gemini-2.5-pro", "--model", "-m", help="LLM model to use for summaries"),
    stats_only: bool = typer.Option(False, "--stats-only", help="Show only statistics, no AI summary"),
):
    """Generate insights and summaries from your conversation archive."""
    config = get_config()
    llm_ = get_model(model_name)

    # Create store for reading conversations
    store = ActivityLogDirectoryStore(root=config.root / "chats")

    # Just show statistics
    journal_gen = JournalGenerator(store, llm_)
    stats = journal_gen.conversation_stats(days)

    print(f"\\n📊 Conversation Statistics ({days} days)")
    print(f"Total conversations: {stats['total_conversations']}")

    # Generate full summary with AI insights
    try:
        summary = journal_gen.recent_conversations_summary(days)
        print(summary)
    except Exception as e:
        logger.exception(f"Failed to generate journal: {e}")
        raise typer.Exit(code=1)
