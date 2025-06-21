import logging
from pathlib import Path

import typer
from rich.logging import RichHandler
from rich.progress import track

from commonplace import logger
from commonplace._claude import ClaudeImporter
from commonplace._gemini import GeminiImporter
from commonplace._store import ActivityLogDirectoryStore

app = typer.Typer(
    help="commonplace: AI-powered journaling tool",
    pretty_exceptions_enable=False,
)


@app.callback()
def _setup_logging(verbose: bool = typer.Option(False, "--verbose", "-v")):
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.addHandler(RichHandler())


@app.command(name="import")
def import_(path: Path):
    """Import activity logs from a file."""

    if not path.exists():
        logger.error(f"The file {path} does not exist.")
        raise typer.Exit(code=1)
    if not path.is_file():
        logger.error(f"The path {path} is not a file.")
        raise typer.Exit(code=1)

    importers = [GeminiImporter(), ClaudeImporter()]
    importer = next((imp for imp in importers if imp.can_import(path)), None)
    if importer is None:
        logger.error(f"The file {path} is not supported by any available importer.")
        raise typer.Exit(code=1)
    logger.info(f"Using {importer.source} importer for {path}.")

    logs = importer.import_(path)
    logger.info(f"Imported {len(logs)} activity logs from {path}.")

    store = ActivityLogDirectoryStore(root=Path("output"))
    for log in track(logs):
        store.store(log)


@app.command()
def journal():
    """Generate a journal entry."""
    logger.info("Journal command is not yet implemented.")
