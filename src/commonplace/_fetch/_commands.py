"""Fetch entrypoint: run configured fetchers and hand output to the importer."""

import logging
import tempfile
from collections.abc import Sequence
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from commonplace._fetch._types import FetchBlocked, Fetcher, NoSession
from commonplace._import._commands import import_one
from commonplace._logging import logger
from commonplace._progress import Row, on, rows
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

    turned_away: dict[str, FetchBlocked | UncommittedChanges] = {}
    # Contexts exit right to left: the pool waits for its threads before the temporary directory goes.
    with (
        rows(source.name for source in active) as table,
        tempfile.TemporaryDirectory() as tmp,
        ThreadPoolExecutor(max_workers=max(len(active), 1), thread_name_prefix="capture") as pool,
    ):
        captures: dict[Future[list[Path]], Source] = {}
        for source in active:
            try:
                prepared = _prepare(repo, source, all_)
            except UncommittedChanges as e:
                _turn_away(source, table[source.name], e, turned_away)
                continue
            captures[pool.submit(_capture, *prepared, Path(tmp) / source.name, table[source.name])] = source
        # Landing reads and writes the repository, so it stays in this thread, a source at a time, as each is ready.
        for capture in as_completed(captures):
            source = captures[capture]
            # Each source signs in on its own and lands all or nothing, so one turned away leaves the rest worth it.
            try:
                table[source.name].status(_landed(_land(repo, source, capture.result(), table[source.name])))
            except (FetchBlocked, UncommittedChanges) as e:
                _turn_away(source, table[source.name], e, turned_away)
    _raise_turned_away(turned_away)


def _turn_away(
    source: Source,
    row: Row,
    e: FetchBlocked | UncommittedChanges,
    turned_away: dict[str, FetchBlocked | UncommittedChanges],
) -> None:
    """Log and show why `source` lands nothing, and keep it for the end of the run."""
    status, level = next(outcome for kind, outcome in _TURNED_AWAY.items() if isinstance(e, kind))
    logger.log(level, f"{source.name}: {e}")
    row.status(status)
    turned_away[source.name] = e


#: How each way a source is turned away shows on its row, and how loudly it's logged; NoSession before the
#: FetchBlocked it specialises, since a service the user doesn't use isn't a failure.
_TURNED_AWAY: dict[type[Exception], tuple[str, int]] = {
    NoSession: ("not signed in", logging.INFO),
    FetchBlocked: ("blocked", logging.ERROR),
    UncommittedChanges: ("refused: uncommitted changes", logging.ERROR),
}


def _raise_turned_away(turned_away: dict[str, FetchBlocked | UncommittedChanges]) -> None:
    """Fail the run for the sources refused or blocked, once every other source has had its turn."""
    if refused := [path for e in turned_away.values() if isinstance(e, UncommittedChanges) for path in e.paths]:
        raise UncommittedChanges(refused)
    if blocked := [
        name for name, e in turned_away.items() if isinstance(e, FetchBlocked) and not isinstance(e, NoSession)
    ]:
        raise FetchBlocked(
            f"Blocked: {', '.join(blocked)}; see above. Nothing from those was imported, "
            "so re-running costs only the time to fetch again."
        )


def _landed(archives: int) -> str:
    """A finished source's row: how many archives it landed."""
    return "nothing new" if not archives else f"landed {archives} archive{'s' if archives > 1 else ''}"


def _prepare(repo: Commonplace, source: Source, all_: bool) -> tuple[Fetcher, datetime | None, list[Path]]:
    """What `source`'s capture needs from the repository, read before any capture starts, since captures run apart."""
    # Before the fetch, which import would refuse to land, and which can take an hour.
    repo.ensure_unedited(source.tree)
    # What this source has landed, for a fetcher that asks only for what changed since; --all asks for it all.
    previous = (
        [] if all_ else [repo.root / blob.path for blob in repo.blobs(*archive_names(source.name), committed_only=True)]
    )
    # Each capture is stamped before it reads anything, so nothing changed while it ran is missed.
    return source.fetcher(repo.config), last_fetched(previous), previous


def _capture(fetcher: Fetcher, since: datetime | None, previous: list[Path], destination: Path, row: Row) -> list[Path]:
    """Fetch into `destination`, counting on `row`; touches nothing in the repository, so it can run in any thread."""
    destination.mkdir()
    with on(row):
        archives = fetcher.fetch(destination, since, previous=previous)
    row.end()
    return archives


def _land(repo: Commonplace, source: Source, archives: list[Path], row: Row) -> int:
    """Import a source's capture as one commit; returns how many archives landed."""
    if not archives:
        logger.info(f"Nothing new from {source.name}")
        return 0
    # The row counted the capture; landing renders in other units, so any bars of its own go beneath.
    row.status("landing")
    # One fetch is one commit, however many archives it wrote; a mirror commits its own.
    stored = [b.path.as_posix() for a in archives if (b := import_one(a, repo, repo.config.user, commit=False))]
    repo.commit(_message(source.name, stored))
    return len(stored)


def _message(source: str, blobs: list[str]) -> str:
    """Name the stored archives, since the temporary ones are gone by the time anyone reads the commit."""
    if len(blobs) == 1:
        return f"Fetch {source}: {blobs[0]}"
    return f"Fetch {source}: {len(blobs)} archives\n\n" + "\n".join(blobs)
