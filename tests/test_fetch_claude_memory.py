"""Tests for the claude.ai memory fetcher, and its path through `fetch` into the mirror."""

import json
from datetime import UTC, datetime

import httpx

from commonplace._fetch._claude_memory import ClaudeMemoryFetcher
from commonplace._fetch._commands import fetch
from commonplace._wire import read_entries, read_header
from tests.porcelain import git

ORG = "org-uuid-1"
TEST_COOKIES = {"sessionKey": "sk-test", "lastActiveOrg": ORG}

LISTING = [
    {"path": "/topics/old.md", "display_name": "Old", "updated_at": "2026-06-01T00:00:00Z"},
    {"path": "/topics/new.md", "display_name": "New", "updated_at": "2026-07-15T00:00:00Z"},
]


class FakeMemory:
    """Stands in for the two melange endpoints, recording what was asked."""

    def __init__(self, listing=LISTING):
        self.listing = listing
        self.requests: list[tuple[str, str, dict]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.requests.append((request.method, request.url.path, body))
        prefix = f"/api/organizations/{ORG}/melange/"
        if request.url.path == prefix + "list":
            return httpx.Response(200, json={"data": self.listing, "categories": []}, headers={"request-id": "req_1"})
        if request.url.path == prefix + "read":
            entry = next(e for e in self.listing if e["path"] == body["path"])
            return httpx.Response(200, json=entry | {"content": f"About {body['path']}\n", "version": "abc"})
        return httpx.Response(404)

    def fetcher(self, cookies=TEST_COOKIES) -> ClaudeMemoryFetcher:
        return ClaudeMemoryFetcher(cookies=cookies, transport=httpx.MockTransport(self))


def test_fetch_without_org_returns_none(tmp_path):
    assert FakeMemory().fetcher(cookies={"sessionKey": "sk"}).fetch(tmp_path, since=None) is None


def test_fetch_everything_records_one_list_and_a_read_per_path(tmp_path):
    archive = FakeMemory().fetcher().fetch(tmp_path, since=None)

    assert read_header(archive).source == "claude-memory"
    entries = list(read_entries(archive))
    assert [(e["endpoint"], e.get("path")) for e in entries] == [
        ("list", None),
        ("read", "/topics/old.md"),
        ("read", "/topics/new.md"),
    ]
    assert entries[0]["request_id"] == "req_1"


def test_fetch_posts_strict_bodies(tmp_path):
    """The API rejects extra request fields, so the bodies are exactly these."""
    memory = FakeMemory()
    memory.fetcher().fetch(tmp_path, since=None)

    assert [(method, body) for method, _, body in memory.requests] == [
        ("POST", {}),
        ("POST", {"path": "/topics/old.md"}),
        ("POST", {"path": "/topics/new.md"}),
    ]


def test_fetch_stores_response_bodies_verbatim(tmp_path):
    raw = '{"data": [], "categories": [], "n": 1e5, "u": "\\/x"}'
    transport = httpx.MockTransport(lambda request: httpx.Response(200, text=raw))
    archive = ClaudeMemoryFetcher(cookies=TEST_COOKIES, transport=transport).fetch(tmp_path, since=None)

    assert [e["response"] for e in read_entries(archive)] == [raw]


def test_fetch_incremental_reads_only_paths_newer_than_the_cursor(tmp_path):
    archive = FakeMemory().fetcher().fetch(tmp_path, since=datetime(2026, 7, 1, tzinfo=UTC))

    assert [e.get("path") for e in read_entries(archive)] == [None, "/topics/new.md"]


def test_fetch_incremental_with_nothing_newer_still_records_the_listing(tmp_path):
    """The listing is the only evidence of a deletion, so it is captured even when nothing is read."""
    archive = FakeMemory().fetcher().fetch(tmp_path, since=datetime(2026, 8, 1, tzinfo=UTC))

    assert [e["endpoint"] for e in read_entries(archive)] == ["list"]


def test_fetch_command_mirrors_into_memory_tree(test_repo):
    fetch(test_repo, fetchers=[FakeMemory().fetcher()], auto_index=False)

    landed = {p.name for p in (test_repo.root / "memory" / "claude" / "topics").iterdir()}
    assert landed == {"old.md", "new.md"}
    assert list((test_repo.root / "chats").rglob("*.md")) == []


def test_fetch_command_cursor_comes_from_the_memory_tree(test_repo):
    """A second run finds nothing newer than the commit the first one made under memory/claude/."""
    memory = FakeMemory()
    fetch(test_repo, fetchers=[memory.fetcher()], auto_index=False)
    head = git(test_repo.root, "rev-parse", "HEAD")
    memory.requests.clear()

    fetch(test_repo, fetchers=[memory.fetcher()], auto_index=False)

    assert [path.rsplit("/", 1)[-1] for _, path, _ in memory.requests] == ["list"]
    assert git(test_repo.root, "rev-parse", "HEAD") == head


def test_fetch_command_upstream_deletion_alone_is_pruned(test_repo):
    memory = FakeMemory()
    fetch(test_repo, fetchers=[memory.fetcher()], auto_index=False)

    memory.listing = LISTING[1:]
    fetch(test_repo, fetchers=[memory.fetcher()], auto_index=False)

    landed = {p.name for p in (test_repo.root / "memory" / "claude" / "topics").iterdir()}
    assert landed == {"new.md"}
