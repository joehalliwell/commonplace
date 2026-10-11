"""Tests for the scheduled-run fetcher, and its archive's path through the paired importer."""

from datetime import UTC, datetime
from pathlib import Path

import httpx

from commonplace._fetch._claude_tasks import ClaudeTasksFetcher
from commonplace._fetch._commands import fetch
from commonplace._wire import read_entries, read_header

TEST_COOKIES = {"sessionKey": "sk-test", "lastActiveOrg": "org-uuid-1"}

RUNS = [
    {
        "id": "cse_new",
        "trigger_id": "trig_1",
        "title": "Digest",
        "created_at": "2026-07-15T05:00:00Z",
        "last_event_at": "2026-07-15T05:03:00Z",
    },
    {
        "id": "cse_old",
        "trigger_id": "trig_1",
        "title": "Digest",
        "created_at": "2026-06-01T05:00:00Z",
        "last_event_at": "2026-06-01T05:03:00Z",
    },
]


def _events(sid: str) -> list[dict]:
    """A prompt, the run's reply, and the result repeating it, newest first as the API sends them."""
    at = next(r["created_at"] for r in RUNS if r["id"] == sid)
    prompt = {"type": "user", "message": {"role": "user", "content": "Go."}}
    text = f"[AI] Headline of {sid}\n\nOutput of {sid}"
    reply = {"type": "assistant", "timestamp": at, "message": {"role": "assistant", "content": text}}
    result = {"type": "result", "result": text}
    return [
        {"event_type": p["type"], "sequence_num": str(n), "created_at": at, "payload": p}
        for n, p in ((3, result), (2, reply), (1, prompt))
    ]


class FakeSessions:
    """Stands in for the sessions listing and event log, each served `page_size` items a page."""

    def __init__(self, page_size: int = 50):
        self.page_size = page_size
        self.requests: list[httpx.Request] = []

    def _page(self, items: list[dict], request: httpx.Request) -> httpx.Response:
        start = int(request.url.params.get("cursor", 0))
        body: dict = {"data": items[start : start + self.page_size]}
        if start + self.page_size < len(items):
            body["next_cursor"] = str(start + self.page_size)
        return httpx.Response(200, json=body, headers={"request-id": f"req_{len(self.requests)}"})

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.headers.get("anthropic-version") != "2023-06-01":
            return httpx.Response(400, json={"error": {"message": "anthropic-version: header is required"}})
        path = request.url.path
        if path == "/v1/code/sessions":
            return self._page(RUNS, request)
        if path.startswith("/v1/code/sessions/") and path.endswith("/events"):
            return self._page(_events(path.split("/")[-2]), request)
        return httpx.Response(404)

    def fetcher(self) -> ClaudeTasksFetcher:
        return ClaudeTasksFetcher(cookies=TEST_COOKIES, transport=httpx.MockTransport(self))


def test_fetch_records_the_listing_then_each_runs_events(tmp_path):
    archive = FakeSessions().fetcher().fetch(tmp_path, since=None)

    assert read_header(archive).source == "claude-tasks"
    assert [(e["endpoint"], e.get("sid")) for e in read_entries(archive)] == [
        ("sessions", None),
        ("events", "cse_new"),
        ("events", "cse_old"),
    ]


def test_fetch_lists_only_trigger_sessions(tmp_path):
    """Without `exclude_tags` the server returns no runs at all, so the query is exactly this."""
    sessions = FakeSessions()
    sessions.fetcher().fetch(tmp_path, since=None)

    assert dict(sessions.requests[0].url.params) == {
        "only_trigger_sessions": "true",
        "limit": "200",
        "exclude_tags": "-",
    }


def test_fetch_follows_cursors_through_every_page(tmp_path):
    archive = FakeSessions(page_size=1).fetcher().fetch(tmp_path, since=None)

    entries = list(read_entries(archive))
    assert [(e["endpoint"], e.get("sid"), e.get("cursor")) for e in entries] == [
        ("sessions", None, None),
        ("sessions", None, "1"),
        ("events", "cse_new", None),
        ("events", "cse_new", "1"),
        ("events", "cse_new", "2"),
        ("events", "cse_old", None),
        ("events", "cse_old", "1"),
        ("events", "cse_old", "2"),
    ]


def test_fetch_stores_response_bodies_verbatim(tmp_path):
    raw_list = '{"data": [{"id": "cse_1", "last_event_at": "2026-07-15T00:00:00Z", "n": 1e5}]}'
    raw_events = '{"data": [], "u": "\\/x"}'

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=raw_events if request.url.path.endswith("/events") else raw_list)

    transport = httpx.MockTransport(handler)
    archive = ClaudeTasksFetcher(cookies=TEST_COOKIES, transport=transport).fetch(tmp_path, since=None)

    assert [e["response"] for e in read_entries(archive)] == [raw_list, raw_events]


def test_fetch_with_nothing_fresh_returns_none(tmp_path):
    assert FakeSessions().fetcher().fetch(tmp_path, since=datetime(2026, 8, 1, tzinfo=UTC)) is None


def test_fetch_incremental_reads_runs_with_events_after_the_cursor(tmp_path):
    """A follow-up typed into an old run's chat moves its `last_event_at`, so it is read again."""
    archive = FakeSessions().fetcher().fetch(tmp_path, since=datetime(2026, 7, 1, tzinfo=UTC))

    assert [e.get("sid") for e in read_entries(archive)] == [None, "cse_new"]


def test_fetch_command_lands_runs_under_their_own_tree(test_repo):
    """Not `chats/claude/`: the fetch cursor is read from the landing tree, and chats would move it."""
    fetch(test_repo, fetchers=[FakeSessions().fetcher()], auto_index=False)

    landed = sorted(p.relative_to(test_repo.root).as_posix() for p in (Path(test_repo.root) / "chats").rglob("*.md"))
    assert landed == [
        "chats/claude-tasks/2026/06/2026-06-01-digest-0500.md",
        "chats/claude-tasks/2026/07/2026-07-15-digest-0500.md",
    ]
    assert "title: '[AI] Headline of cse_new'" in (Path(test_repo.root) / landed[1]).read_text()
