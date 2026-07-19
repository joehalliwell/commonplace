"""Fetch entrypoint: run configured fetchers and hand output to the importer."""

import tempfile
from pathlib import Path

from commonplace._fetch._claude import ClaudeFetcher
from commonplace._fetch._gemini import GeminiFetcher
from commonplace._fetch._types import Fetcher
from commonplace._import._commands import import_
from commonplace._logging import logger
from commonplace._repo import Commonplace

FETCHERS: list[Fetcher] = [
    ClaudeFetcher(),
    GeminiFetcher(),
]


def fetch(repo: Commonplace, sources: list[str] | None = None, auto_index: bool | None = None) -> None:
    """Fetch new content from each configured source and import it."""
    active = FETCHERS
    if sources:
        active = [f for f in FETCHERS if f.source in sources]
        if not active:
            logger.error(f"No fetchers match sources: {sources}")
            return

    for fetcher in active:
        logger.info(f"Fetching from {fetcher.source}")
        with tempfile.TemporaryDirectory() as tmp:
            artifact = fetcher.fetch(Path(tmp), repo)
            if artifact is None:
                logger.info(f"Nothing new from {fetcher.source}")
                continue
            import_(artifact, repo, user=repo.config.user, prefix="chats", auto_index=auto_index)
