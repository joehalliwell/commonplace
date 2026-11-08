"""Tests for the `fetch` command's own logic, against stub fetchers.

Its path through a real fetcher and importer is covered beside each provider's fake.
"""

from datetime import UTC, datetime

import pytest

from commonplace._fetch._commands import fetch
from commonplace._fetch._helpers import FetchBlocked, NoSession
from commonplace._wire import archive_name, write_archive
from tests.fetching import fetching


def test_a_blocked_source_does_not_stop_the_others(test_repo):
    """Each source signs in on its own, so one dead session leaves the rest worth fetching."""
    called: list[str] = []

    class Blocked:
        source = "blocked"

        def fetch(self, destination, since, previous=()):
            raise FetchBlocked("Blocked rejected the session.")

    class Stub:
        source = "stub"

        def fetch(self, destination, since, previous=()):
            called.append("stub")
            return []

    with pytest.raises(FetchBlocked, match="blocked"):
        fetch(test_repo, sources=fetching(Blocked(), Stub()), auto_index=False)
    assert called == ["stub"]


def test_a_source_with_no_session_is_skipped_without_failing_the_run(test_repo):
    """No cookie at all means a service the user doesn't use, which isn't a failure."""
    called: list[str] = []

    class Unused:
        source = "unused"

        def fetch(self, destination, since, previous=()):
            raise NoSession("Unused rejected the session: Chrome holds no session cookie.")

    class Stub:
        source = "stub"

        def fetch(self, destination, since, previous=()):
            called.append("stub")
            return []

    fetch(test_repo, sources=fetching(Unused(), Stub()), auto_index=False)
    assert called == ["stub"]


def test_fetch_command_filters_by_source(test_repo):
    called: list[str] = []

    class Stub:
        source = "stub"

        def fetch(self, destination, since, previous=()):
            called.append("stub")
            return []

    fetch(test_repo, names=["nonexistent"], sources=fetching(Stub()), auto_index=False)
    assert called == []

    fetch(test_repo, names=["stub"], sources=fetching(Stub()), auto_index=False)
    assert called == ["stub"]


class _Recording:
    """A fetcher that records the cursor it is given and fetches nothing."""

    source = "recording"

    def __init__(self) -> None:
        self.since: list[datetime | None] = []

    def fetch(self, destination, since, previous=()):
        self.since.append(since)
        return []


def _store_capture(repo, tmp_path, source: str, fetched_at: datetime) -> None:
    folder = tmp_path / fetched_at.isoformat()
    folder.mkdir()
    repo.store_blob(write_archive(folder / archive_name(source), source, [], fetched_at=fetched_at))


def test_fetch_cursor_is_when_the_newest_stored_capture_of_the_source_was_fetched(test_repo, tmp_path):
    newest = datetime(2026, 3, 2, tzinfo=UTC)
    for source, fetched_at in [("recording", datetime(2026, 3, 1, tzinfo=UTC)), ("recording", newest)]:
        _store_capture(test_repo, tmp_path, source, fetched_at)
    _store_capture(test_repo, tmp_path, "other", datetime(2026, 4, 1, tzinfo=UTC))
    test_repo.commit("Seed captures", auto_index=False)
    recording = _Recording()

    fetch(test_repo, sources=fetching(recording), auto_index=False)
    fetch(test_repo, sources=fetching(recording), auto_index=False, all_=True)

    assert recording.since == [newest, None]


def test_fetch_without_a_stamped_capture_fetches_everything(test_repo, make_note):
    """Notes in the source's tree, from an export, say nothing about when the vendor was last read."""
    test_repo.save(make_note("chats/recording/seed.md", "# seed\n"))
    test_repo.commit("Seed recording", auto_index=False)
    recording = _Recording()

    fetch(test_repo, sources=fetching(recording), auto_index=False)

    assert recording.since == [None]
