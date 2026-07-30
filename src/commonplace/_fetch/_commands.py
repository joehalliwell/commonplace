"""Fetch entrypoint: run configured fetchers and hand output to the importer."""

import tempfile
from pathlib import Path

from commonplace._fetch._chatgpt import ChatGptFetcher
from commonplace._fetch._claude import ClaudeFetcher
from commonplace._fetch._gemini import GeminiFetcher
from commonplace._fetch._types import Fetcher
from commonplace._import._commands import import_
from commonplace._logging import logger
from commonplace._repo import Commonplace

FETCHERS: list[Fetcher] = [
    ClaudeFetcher(),
    GeminiFetcher(),
    ChatGptFetcher(),
]


def fetch(
    repo: Commonplace,
    sources: list[str] | None = None,
    auto_index: bool | None = None,
    fetchers: list[Fetcher] | None = None,
    all_: bool = False,
) -> None:
    """Fetch new content from each configured source and import it.

    If `all_` is True, the git-derived cursor is bypassed and every remote
    conversation is fetched. Useful for recovery when the cursor is wrong,
    or for a first-time bulk import."""
    pool = fetchers if fetchers is not None else FETCHERS
    active = pool
    if sources:
        active = [f for f in pool if f.source in sources]
        if not active:
            logger.error(f"No fetchers match sources: {sources}")
            return

    for fetcher in active:
        logger.info(f"Fetching from {fetcher.source}")
        # `diff_filter="AM"` excludes rename-source / pure-deletion commits so
        # a `git mv chats/{source}/ elsewhere` doesn't poison the cursor.
        since = None if all_ else repo.last_commit_time(f"chats/{fetcher.source}/", diff_filter="AM")
        with tempfile.TemporaryDirectory() as tmp:
            artifact = fetcher.fetch(Path(tmp), since)
            if artifact is None:
                logger.info(f"Nothing new from {fetcher.source}")
                continue
            import_(artifact, repo, user=repo.config.user, prefix="chats", auto_index=auto_index)
