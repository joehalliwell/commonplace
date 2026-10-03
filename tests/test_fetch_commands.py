"""Tests for the `fetch` command's own logic, against stub fetchers.

Its path through a real fetcher and importer is covered beside each provider's fake.
"""

from commonplace._fetch._commands import fetch


def test_fetch_command_filters_by_source(test_repo):
    called: list[str] = []

    class Stub:
        source = "stub"

        def fetch(self, destination, since):
            called.append("stub")

    fetch(test_repo, sources=["nonexistent"], fetchers=[Stub()], auto_index=False)
    assert called == []

    fetch(test_repo, sources=["stub"], fetchers=[Stub()], auto_index=False)
    assert called == ["stub"]


def test_fetch_command_all_flag_bypasses_cursor(test_repo, make_note):
    """With all_=True, the fetcher is called with since=None regardless of
    what the repo's git history would otherwise say."""
    calls: list[str | None] = []

    class RecordingStub:
        source = "recording"

        def fetch(self, destination, since):
            calls.append(since)

    # Seed the repo with a chats/recording/ commit so last_commit_time would
    # return a non-None cursor without --all.
    test_repo.save(make_note("chats/recording/seed.md", "# seed\n"))
    test_repo.commit("Seed recording", auto_index=False)

    fetch(test_repo, fetchers=[RecordingStub()], auto_index=False)
    assert calls[-1] is not None, "without --all, cursor should reflect the seed commit"

    fetch(test_repo, fetchers=[RecordingStub()], auto_index=False, all_=True)
    assert calls[-1] is None, "with --all, cursor is bypassed"
