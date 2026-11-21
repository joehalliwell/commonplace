"""Tests for the scheduled-run fetcher, and its archive's path through the paired importer."""

from datetime import UTC, datetime
from pathlib import Path

import httpx

from commonplace._fetch._claude_tasks import ClaudeTasksFetcher
from commonplace._fetch._commands import fetch
from commonplace._wire import read_entries, read_header
from tests.fetching import fetching, owned

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


CHATS = [
    {"uuid": "chat-new", "name": "Digest", "created_at": "2026-11-20T06:00:00Z", "updated_at": "2026-11-20T06:03:00Z"},
    {"uuid": "chat-old", "name": "Digest", "created_at": "2026-06-02T06:00:00Z", "updated_at": "2026-06-02T06:03:00Z"},
]


def _chat(cid: str) -> dict:
    """A routine run as claude.ai serves it with its tool calls: the prompt, then the run's reply."""
    listed = next(c for c in CHATS if c["uuid"] == cid)
    at = listed["created_at"]
    reply = [
        {"type": "tool_use", "name": "web_search", "input": {"query": "news"}},
        {"type": "text", "text": f"[AI] Headline of {cid}\n\nOutput of {cid}"},
    ]
    messages = [
        {
            "uuid": "m1",
            "sender": "human",
            "created_at": at,
            "text": "Go.",
            "content": [{"type": "text", "text": "Go."}],
        },
        {
            "uuid": "m2",
            "sender": "assistant",
            "created_at": at,
            "text": "",
            "stop_reason": "end_turn",
            "content": reply,
        },
    ]
    return {**listed, "platform": "ROUTINE_RUN", "model": "claude-opus-5-5", "chat_messages": messages}


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
        path = request.url.path
        if not path.startswith("/v1/code/"):
            return self._chats(request)
        if request.headers.get("anthropic-version") != "2023-06-01":
            return httpx.Response(400, json={"error": {"message": "anthropic-version: header is required"}})
        if path == "/v1/code/sessions":
            return self._page(RUNS, request)
        if path.startswith("/v1/code/sessions/") and path.endswith("/events"):
            return self._page(_events(path.split("/")[-2]), request)
        return httpx.Response(404)

    def _chats(self, request: httpx.Request) -> httpx.Response:
        """The claude.ai chat API, which lists routine runs only when asked for their platform."""
        path = request.url.path.removeprefix("/api/organizations/org-uuid-1")
        if path == "/chat_conversations":
            routine = request.url.params.get_list("platforms") == ["ROUTINE_RUN"]
            return httpx.Response(200, json=CHATS if routine else [])
        if path.startswith("/chat_conversations/"):
            return httpx.Response(200, json=_chat(path.split("/")[-1]))
        return httpx.Response(404)

    def fetcher(self) -> ClaudeTasksFetcher:
        return owned(ClaudeTasksFetcher, cookies=TEST_COOKIES, transport=httpx.MockTransport(self))


def _read(entries) -> list[tuple]:
    """What each entry recorded: its endpoint and the run or chat it is about."""
    return [(e["endpoint"], e.get("sid") or e.get("cid")) for e in entries]


def test_fetch_records_the_listings_then_each_run(tmp_path):
    [archive] = FakeSessions().fetcher().fetch(tmp_path, since=None)

    assert read_header(archive).source == "claude-tasks"
    assert _read(read_entries(archive)) == [
        ("sessions", None),
        ("events", "cse_new"),
        ("events", "cse_old"),
        ("conversations", None),
        ("conversation", "chat-new"),
        ("conversation", "chat-old"),
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


def test_fetch_lists_routine_run_chats_by_their_platform(tmp_path):
    """The default chat listing leaves routine runs out."""
    sessions = FakeSessions()
    sessions.fetcher().fetch(tmp_path, since=None)

    [listing] = [r for r in sessions.requests if r.url.path.endswith("/chat_conversations")]
    assert listing.url.params.get_list("platforms") == ["ROUTINE_RUN"]


def test_fetch_reads_routine_run_chats_with_their_tool_calls(tmp_path):
    """`raw` rendering replaces each tool call with a placeholder."""
    sessions = FakeSessions()
    sessions.fetcher().fetch(tmp_path, since=None)

    read = [r for r in sessions.requests if "/chat_conversations/" in r.url.path]
    assert {(r.url.params["rendering_mode"], r.url.params["render_all_tools"]) for r in read} == {("messages", "true")}


def test_fetch_follows_cursors_through_every_page(tmp_path):
    [archive] = FakeSessions(page_size=1).fetcher().fetch(tmp_path, since=None)

    entries = [e for e in read_entries(archive) if e["endpoint"] in {"sessions", "events"}]
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
    raw_chats = '[{"uuid": "c1", "updated_at": "2026-11-20T00:00:00Z", "n": 1e5}]'
    raw_chat = '{"uuid": "c1", "u": "\\/x"}'

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.startswith("/v1/code/"):
            return httpx.Response(200, text=raw_events if path.endswith("/events") else raw_list)
        return httpx.Response(200, text=raw_chats if path.endswith("/chat_conversations") else raw_chat)

    transport = httpx.MockTransport(handler)
    [archive] = owned(ClaudeTasksFetcher, cookies=TEST_COOKIES, transport=transport).fetch(tmp_path, since=None)

    assert [e["response"] for e in read_entries(archive)] == [raw_list, raw_events, raw_chats, raw_chat]


def test_fetch_with_nothing_fresh_returns_none(tmp_path):
    assert FakeSessions().fetcher().fetch(tmp_path, since=datetime(2026, 12, 1, tzinfo=UTC)) == []


def test_fetch_incremental_reads_runs_active_after_the_cursor(tmp_path):
    """A follow-up typed into an old run moves its `last_event_at`, or a chat's `updated_at`, so it is read again."""
    [archive] = FakeSessions().fetcher().fetch(tmp_path, since=datetime(2026, 7, 1, tzinfo=UTC))

    assert _read(read_entries(archive)) == [
        ("sessions", None),
        ("events", "cse_new"),
        ("conversations", None),
        ("conversation", "chat-new"),
    ]


def test_fetch_command_lands_runs_under_their_own_tree(test_repo):
    """Not `chats/claude/`, even for a run that is a chat: a run is what a routine did, not something said."""
    fetch(test_repo, sources=fetching(FakeSessions().fetcher()))

    landed = sorted(p.relative_to(test_repo.root).as_posix() for p in (Path(test_repo.root) / "chats").rglob("*.md"))
    assert landed == [
        "chats/claude-tasks/2026/06/2026-06-01-ai-headline-of-cseold.md",
        "chats/claude-tasks/2026/06/2026-06-02-ai-headline-of-chat-old.md",
        "chats/claude-tasks/2026/07/2026-07-15-ai-headline-of-csenew.md",
        "chats/claude-tasks/2026/11/2026-11-20-ai-headline-of-chat-new.md",
    ]
