"""Fetch entrypoint: run configured fetchers and hand output to the importer."""

import tempfile
from collections.abc import Sequence
from pathlib import Path

from commonplace._fetch._helpers import FetchBlocked, NoSession
from commonplace._import._commands import import_one
from commonplace._logging import logger
from commonplace._progress import on, rows
from commonplace._repo import Commonplace, UncommittedChanges
from commonplace._sources import SOURCES
from commonplace._types import Source
from commonplace._wire import archive_names, last_fetched


def fetch(
    repo: Commonplace,
    names: list[str] | None = None,
    sources: Sequence[Source] = SOURCES,
    all_: bool = False,
) -> None:
    """Fetch what is new from each source with a fetcher, or those `names` names, and import it.

    If `all_` is True, the cursor is bypassed and everything the
    remote has is fetched. Useful for recovery when the cursor is wrong,
    or for a first-time bulk import."""
    active = [source for source in sources if source.fetcher_type is not None and (not names or source.name in names)]
    if names and not active:
        logger.error(f"No fetchers match sources: {names}")
        return

    blocked: list[str] = []
    refused: list[Path] = []
    with rows(source.name for source in active) as table:
        for source in active:
            row = table[source.name]
            logger.info(f"Fetching from {source.name}")
            # Each source signs in on its own and lands all or nothing, so one turned away leaves the rest worth fetching.
            try:
                with on(row):
                    row.status(_landed(_fetch_one(repo, source, all_)))
            except NoSession:
                logger.info(f"Skipping {source.name}: not signed in")
                row.status("not signed in")
            except FetchBlocked as e:
                logger.error(str(e))
                blocked.append(source.name)
                row.status("blocked")
            except UncommittedChanges as e:
                logger.error(f"Not fetching {source.name}: {e}")
                refused += e.paths
                row.status("refused: uncommitted changes")
    if refused:
        raise UncommittedChanges(refused)
    if blocked:
        raise FetchBlocked(
            f"Blocked: {', '.join(blocked)}; see above. Nothing from those was imported, "
            "so re-running costs only the time to fetch again."
        )


def _landed(archives: int) -> str:
    """A finished source's row: how many archives it landed."""
    return "nothing new" if not archives else f"landed {archives} archive{'s' if archives > 1 else ''}"


def _fetch_one(repo: Commonplace, source: Source, all_: bool) -> int:
    """Fetch what is new from one source and import it; returns how many archives landed."""
    # Before the fetch, which import would refuse to land, and which can take an hour.
    repo.ensure_unedited(source.tree)
    fetcher = source.fetcher(repo.config)
    # What this source has landed, for a fetcher that asks only for what changed since; --all asks for it all.
    previous = (
        [] if all_ else [repo.root / blob.path for blob in repo.blobs(*archive_names(source.name), committed_only=True)]
    )
    # Each capture is stamped before it reads anything, so nothing changed while it ran is missed.
    since = last_fetched(previous)
    with tempfile.TemporaryDirectory() as tmp:
        archives = fetcher.fetch(Path(tmp), since, previous=previous)
        if not archives:
            logger.info(f"Nothing new from {source.name}")
            return 0
        # One fetch is one commit, however many archives it wrote; a mirror commits its own.
        stored = [b.path.as_posix() for a in archives if (b := import_one(a, repo, repo.config.user, commit=False))]
        repo.commit(_message(source.name, stored))
        return len(stored)


def _message(source: str, blobs: list[str]) -> str:
    """Name the stored archives, since the temporary ones are gone by the time anyone reads the commit."""
    if len(blobs) == 1:
        return f"Fetch {source}: {blobs[0]}"
    return f"Fetch {source}: {len(blobs)} archives\n\n" + "\n".join(blobs)
