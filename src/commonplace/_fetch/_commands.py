"""Fetch entrypoint: run configured fetchers and hand output to the importer."""

import tempfile
from collections.abc import Sequence
from pathlib import Path

from commonplace._fetch._helpers import FetchBlocked, NoSession
from commonplace._import._commands import import_one
from commonplace._logging import logger
from commonplace._repo import Commonplace
from commonplace._sources import SOURCES
from commonplace._types import Source
from commonplace._wire import archive_names


def fetch(
    repo: Commonplace,
    names: list[str] | None = None,
    auto_index: bool | None = None,
    sources: Sequence[Source] = SOURCES,
    all_: bool = False,
) -> None:
    """Fetch what is new from each source with a fetcher, or those `names` names, and import it.

    If `all_` is True, the git-derived cursor is bypassed and everything the
    remote has is fetched. Useful for recovery when the cursor is wrong,
    or for a first-time bulk import."""
    active = [source for source in sources if source.fetcher_type is not None and (not names or source.name in names)]
    if names and not active:
        logger.error(f"No fetchers match sources: {names}")
        return

    blocked: list[str] = []
    for source in active:
        logger.info(f"Fetching from {source.name}")
        # Each source signs in on its own, so one turned away leaves the rest worth fetching.
        try:
            _fetch_one(repo, source, auto_index, all_)
        except NoSession:
            logger.info(f"Skipping {source.name}: not signed in")
        except FetchBlocked as e:
            logger.error(str(e))
            blocked.append(source.name)
    if blocked:
        raise FetchBlocked(
            f"Blocked: {', '.join(blocked)}; see above. Nothing from those was imported, "
            "so re-running costs only the time to fetch again."
        )


def _fetch_one(repo: Commonplace, source: Source, auto_index: bool | None, all_: bool) -> None:
    """Fetch what is new from one source and import it."""
    fetcher = source.fetcher(repo.config)
    # `diff_filter="AM"` excludes rename-source / pure-deletion commits so
    # a `git mv chats/{source}/ elsewhere` doesn't poison the cursor — nor,
    # for a mirrored tree, does a commit that only pruned.
    tree = source.tree.as_posix()
    since = None if all_ else repo.last_commit_time(f"{tree}/", diff_filter="AM")
    # What this source has landed, for a fetcher that asks only for what changed since; --full asks for it all.
    previous = [] if all_ else [repo.root / p for p in repo.stored_archives(*archive_names(source.name))]
    with tempfile.TemporaryDirectory() as tmp:
        archives = fetcher.fetch(Path(tmp), since, previous=previous)
        if not archives:
            logger.info(f"Nothing new from {source.name}")
            return
        # One fetch is one commit, however many archives it wrote.
        # A mirror commits its own; it still needs to know whether to index.
        stored = [import_one(a, repo, repo.config.user, auto_index=auto_index, commit=False) for a in archives]
        repo.commit(_message(source.name, [b.path.as_posix() for b in stored if b]), auto_index=auto_index)


def _message(source: str, blobs: list[str]) -> str:
    """Name the stored archives, since the temporary ones are gone by the time anyone reads the commit."""
    if len(blobs) == 1:
        return f"Fetch {source}: {blobs[0]}"
    return f"Fetch {source}: {len(blobs)} archives\n\n" + "\n".join(blobs)
