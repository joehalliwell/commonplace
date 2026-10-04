"""Tests for the ChatGPT memory fetcher, and its path through `fetch` into the mirror."""

import json
from datetime import UTC, datetime

import httpx
import pytest

from commonplace._fetch._chatgpt import ChatGptFetcher
from commonplace._fetch._chatgpt_memory import ChatGptMemoryFetcher
from commonplace._fetch._commands import fetch
from commonplace._wire import read_entries, read_header
from tests.porcelain import git

SESSION_COOKIES = {"__Secure-next-auth.session-token": "tok"}
GENERATED_AT = "2026-10-03T22:27:53.035594+00:00"
SECTIONS = [
    {"id": "overview", "title": "Overview", "description": "Prefers tea."},
    {"id": "work", "title": "Work", "description": "Writes software."},
]


def summary_stream(sections: list[dict], generated_at: str = GENERATED_AT) -> str:
    """The about-you summary as the server streams it, framing and all."""
    head = {"generatedAtIso": generated_at, "sourceChecksum": "0" * 64}
    events = [
        ("started", head),
        (
            "section_types",
            {"generatedAtIso": generated_at, "sections": [{"id": s["id"], "title": s["title"]} for s in sections]},
        ),
        *(("section", {"section": s}) for s in sections),
        ("done", {"emptyStateMessage": "Nothing yet.", **head, "sections": sections}),
    ]
    return "".join(f"event: {name}\ndata: {json.dumps(data)}\n\n" for name, data in events) + "data: [DONE]\n\n"


class FakeMemory:
    """Stands in for the session and the two memory endpoints, recording what was asked."""

    def __init__(self, sections=SECTIONS):
        self.sections = sections
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if path == "/api/auth/session":
            return httpx.Response(200, json={"accessToken": "jwt-token", "user": {}})
        if path == "/backend-api/memories" and request.method == "GET":
            return httpx.Response(200, json={"memories": [], "memory_max_tokens": 5000000, "memory_num_tokens": 0})
        if path == "/backend-api/memories/about_you/summary/stream" and request.method == "POST":
            return httpx.Response(
                200, text=summary_stream(self.sections), headers={"content-type": "text/event-stream"}
            )
        return httpx.Response(405 if path.startswith("/backend-api/memories") else 404)

    def fetcher(self, cookies=SESSION_COOKIES) -> ChatGptMemoryFetcher:
        return ChatGptMemoryFetcher(cookies=cookies, transport=httpx.MockTransport(self))


@pytest.fixture(autouse=True)
def no_request_pacing(monkeypatch):
    monkeypatch.setattr(ChatGptFetcher, "request_interval", 0)


def test_fetch_without_session_cookie_returns_none(tmp_path):
    assert FakeMemory().fetcher(cookies={"cf_clearance": "cf"}).fetch(tmp_path, since=None) is None


def test_fetch_records_saved_memories_then_the_summary(tmp_path):
    archive = FakeMemory().fetcher().fetch(tmp_path, since=None)

    assert read_header(archive).source == "chatgpt-memory"
    assert [e["endpoint"] for e in read_entries(archive)] == ["memories", "summary"]


def test_fetch_posts_the_summary_with_the_bearer_token(tmp_path):
    memory = FakeMemory()
    memory.fetcher().fetch(tmp_path, since=None)

    [summary] = [r for r in memory.requests if r.url.path.endswith("/stream")]
    assert summary.method == "POST"
    assert summary.headers["Authorization"] == "Bearer jwt-token"


def test_fetch_stores_the_stream_verbatim(tmp_path):
    archive = FakeMemory().fetcher().fetch(tmp_path, since=None)

    assert list(read_entries(archive))[1]["response"] == summary_stream(SECTIONS)


def test_fetch_with_a_cursor_still_records_everything(tmp_path):
    """Neither endpoint can be asked for changes only, so the cursor has nothing to narrow."""
    archive = FakeMemory().fetcher().fetch(tmp_path, since=datetime(2099, 1, 1, tzinfo=UTC))

    assert [e["endpoint"] for e in read_entries(archive)] == ["memories", "summary"]


def test_fetch_command_mirrors_each_section_into_the_memory_tree(test_repo):
    fetch(test_repo, fetchers=[FakeMemory().fetcher()], auto_index=False)

    landed = {p.name for p in (test_repo.root / "memory" / "chatgpt").iterdir()}
    assert landed == {"overview.md", "work.md"}


def test_fetch_command_unchanged_summary_makes_no_commit(test_repo):
    memory = FakeMemory()
    fetch(test_repo, fetchers=[memory.fetcher()], auto_index=False)
    head = git(test_repo.root, "rev-parse", "HEAD")

    fetch(test_repo, fetchers=[memory.fetcher()], auto_index=False)

    assert git(test_repo.root, "rev-parse", "HEAD") == head


def test_fetch_command_section_dropped_upstream_is_pruned(test_repo):
    memory = FakeMemory()
    fetch(test_repo, fetchers=[memory.fetcher()], auto_index=False)

    memory.sections = SECTIONS[1:]
    fetch(test_repo, fetchers=[memory.fetcher()], auto_index=False)

    assert {p.name for p in (test_repo.root / "memory" / "chatgpt").iterdir()} == {"work.md"}
