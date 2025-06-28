import logging
from pathlib import Path

import typer
from rich.logging import RichHandler
from rich.progress import track

from commonplace import get_config, LOGGER
from commonplace._claude import ClaudeImporter
from commonplace._gemini import GeminiImporter
from commonplace._store import ActivityLogDirectoryStore, MarkdownSerializer

app = typer.Typer(
    help="commonplace: AI-powered journaling tool",
    pretty_exceptions_enable=False,
)


@app.callback()
def _setup_logging(verbose: bool = typer.Option(False, "--verbose", "-v")):
    LOGGER.setLevel(logging.DEBUG if verbose else logging.INFO)
    LOGGER.addHandler(RichHandler())


@app.command(name="import")
def import_(path: Path):
    """Import activity logs from a file."""

    try:
        if not path.exists():
            LOGGER.error(f"The file {path} does not exist.")
            raise typer.Exit(code=1)
        if not path.is_file():
            LOGGER.error(f"The path {path} is not a file.")
            raise typer.Exit(code=1)
    except PermissionError:
        LOGGER.exception(f"Permission denied accessing {path}")
        raise typer.Exit(code=1)
    except OSError:
        LOGGER.exception(f"Error accessing {path}")
        raise typer.Exit(code=1)

    importers = [GeminiImporter(), ClaudeImporter()]
    importer = next((imp for imp in importers if imp.can_import(path)), None)
    if importer is None:
        LOGGER.error(f"The file {path} is not supported by any available importer.")
        raise typer.Exit(code=1)
    LOGGER.info(f"Using {importer.source} importer for {path}.")

    try:
        logs = importer.import_(path)
        LOGGER.info(f"Imported {len(logs)} activity logs from {path}.")
    except Exception:
        LOGGER.exception(f"Failed to import from {path}")
        raise typer.Exit(code=1)

    try:
        store = ActivityLogDirectoryStore(
            root=get_config().root / "chats",
            serializer=MarkdownSerializer(human="Joe", assistant=importer.source.title()),
        )
        for log in track(logs):
            store.store(log)
        LOGGER.info(f"Successfully stored {len(logs)} logs")
    except Exception:
        LOGGER.exception("Failed to store logs")
        raise typer.Exit(code=1)


@app.command()
def journal():
    """Generate a journal entry."""
    LOGGER.info("Journal command is not yet implemented.")
