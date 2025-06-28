import logging
from pathlib import Path

import typer
from rich.logging import RichHandler
from rich.progress import track

from commonplace import get_config, logger
from commonplace._claude import ClaudeImporter
from commonplace._gemini import GeminiImporter
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
        store = ActivityLogDirectoryStore(
            root=get_config().root / "chats",
            serializer=MarkdownSerializer(human="Joe", assistant=importer.source.title()),
        )
        for log in track(logs):
            store.store(log)
        logger.info(f"Successfully stored {len(logs)} logs")
    except Exception:
        logger.exception("Failed to store logs")
        raise typer.Exit(code=1)


@app.command()
def journal():
    """Generate insights and summaries from your conversation archive (coming soon)."""
    logger.info(
        "Journal command is not yet implemented. This will analyze your conversation archive to generate insights and summaries."
    )
