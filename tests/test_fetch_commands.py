"""Tests for the `fetch` command's own logic, against stub fetchers.

Its path through a real fetcher and importer is covered beside each provider's fake.
"""

import threading
from datetime import UTC, datetime

import pytest

from commonplace import _repo
from commonplace._fetch._claude_code import ClaudeCodeFetcher
from commonplace._fetch._commands import fetch
from commonplace._fetch._helpers import FetchBlocked, NoSession
from commonplace._progress import tick
from commonplace._repo import UncommittedChanges
from commonplace._wire import archive_name, write_archive
from tests.fetching import fetching, owned
from tests.porcelain import git
from tests.test_fetch_claude_code import _claude_home
from tests.test_keep import FakeKeep


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
        fetch(test_repo, sources=fetching(Blocked(), Stub()))
    assert called == ["stub"]


def test_a_source_refused_for_uncommitted_changes_does_not_stop_the_others(test_repo):
    """Each source lands all or nothing, so refusing one leaves the rest worth fetching."""
    called: list[str] = []

    class Edited:
        source = "edited"

        def fetch(self, destination, since, previous=()):
            called.append("edited")
            return []

    class Stub:
        source = "stub"

        def fetch(self, destination, since, previous=()):
            called.append("stub")
            return []

    [edited, stub] = fetching(Edited(), Stub())
    (test_repo.root / edited.tree).mkdir(parents=True)
    (test_repo.root / edited.tree / "mine.md").write_text("# Mine\n")

    with pytest.raises(UncommittedChanges, match="mine.md"):
        fetch(test_repo, sources=[edited, stub])
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

    fetch(test_repo, sources=fetching(Unused(), Stub()))
    assert called == ["stub"]


def test_fetch_command_filters_by_source(test_repo):
    called: list[str] = []

    class Stub:
        source = "stub"

        def fetch(self, destination, since, previous=()):
            called.append("stub")
            return []

    fetch(test_repo, names=["nonexistent"], sources=fetching(Stub()))
    assert called == []

    fetch(test_repo, names=["stub"], sources=fetching(Stub()))
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
    test_repo.commit("Seed captures")
    recording = _Recording()

    fetch(test_repo, sources=fetching(recording))
    fetch(test_repo, sources=fetching(recording), all_=True)

    assert recording.since == [newest, None]


def test_fetch_cursor_counts_only_committed_captures(test_repo, tmp_path):
    """A capture stored by a run that died before committing isn't in the record yet, so it moves nothing."""
    committed = datetime(2026, 3, 1, tzinfo=UTC)
    _store_capture(test_repo, tmp_path, "recording", committed)
    test_repo.commit("Seed capture")
    _store_capture(test_repo, tmp_path, "recording", datetime(2026, 3, 2, tzinfo=UTC))
    test_repo._pending.clear()  # The run that stored it died before its commit
    recording = _Recording()

    fetch(test_repo, sources=fetching(recording))

    assert recording.since == [committed]


def test_fetch_without_a_stamped_capture_fetches_everything(test_repo, make_note):
    """Notes in the source's tree, from an export, say nothing about when the vendor was last read."""
    test_repo.put(make_note("chats/recording/seed.md", "# seed\n"))
    test_repo.commit("Seed recording")
    recording = _Recording()

    fetch(test_repo, sources=fetching(recording))

    assert recording.since == [None]


def test_fetch_leaves_a_row_per_source_saying_how_it_went(test_repo, capsys):
    class Unused:
        source = "unused"

        def fetch(self, destination, since, previous=()):
            raise NoSession("Unused rejected the session: Chrome holds no session cookie.")

    class Blocked:
        source = "blocked"

        def fetch(self, destination, since, previous=()):
            raise FetchBlocked("Blocked rejected the session.")

    class Quiet:
        source = "quiet"

        def fetch(self, destination, since, previous=()):
            return []

    with pytest.raises(FetchBlocked):
        fetch(test_repo, sources=fetching(Unused(), Blocked(), Quiet()))

    rows = capsys.readouterr().out.splitlines()
    for source, outcome in [("unused", "not signed in"), ("blocked", "blocked"), ("quiet", "nothing new")]:
        assert any(line.lstrip().startswith(source) and outcome in line for line in rows), (source, outcome)


def test_a_sources_row_ends_with_what_its_capture_counted(test_repo, capsys):
    """A pager knows how many pages there were only once it's done; the row says so."""

    class Pager:
        source = "pager"

        def fetch(self, destination, since, previous=()):
            for _ in range(3):
                tick("page")
            return []

    fetch(test_repo, sources=fetching(Pager()))

    assert any(line.lstrip().startswith("pager") and "3/3" in line for line in capsys.readouterr().out.splitlines())


def test_fetch_captures_every_source_at_once(test_repo):
    """A slow source shouldn't hold up the rest: each waits here for the other, which only works side by side."""
    meet = threading.Barrier(2, timeout=5)

    class Slow:
        def __init__(self, source):
            self.source = source

        def fetch(self, destination, since, previous=()):
            meet.wait()
            return []

    fetch(test_repo, sources=fetching(Slow("first"), Slow("second")))


def test_fetch_touches_the_repository_only_from_the_thread_it_was_called_in(test_repo, tmp_path, monkeypatch):
    """Commonplace caches git state that a commit invalidates, so captures in other threads must not read it."""
    callers: set[str] = set()
    real = _repo._run_git

    def run_git(*args, **kwargs):
        callers.add(threading.current_thread().name)
        return real(*args, **kwargs)

    monkeypatch.setattr(_repo, "_run_git", run_git)

    fetch(test_repo, sources=fetching(FakeKeep().fetcher(), owned(ClaudeCodeFetcher, root=_claude_home(tmp_path))))

    assert callers == {threading.current_thread().name}


def test_fetch_lands_each_source_in_a_commit_of_its_own(test_repo, tmp_path):
    before = git(test_repo.root, "rev-parse", "HEAD").strip()

    fetch(test_repo, sources=fetching(FakeKeep().fetcher(), owned(ClaudeCodeFetcher, root=_claude_home(tmp_path))))

    commits = git(test_repo.root, "rev-list", f"{before}..HEAD").split()
    trees = [
        {"/".join(path.split("/")[:2]) for path in _changed(test_repo, c) if not path.startswith(".")} for c in commits
    ]
    assert sorted(map(sorted, trees)) == [["chats/claude-code"], ["notes/keep"]]


def _changed(repo, commit: str) -> list[str]:
    return git(repo.root, "diff-tree", "--no-commit-id", "--name-only", "-r", commit).split()
