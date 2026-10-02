"""Tests for the Claude fetcher, and its archive's path through the paired importer."""

import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

from commonplace._fetch._claude import ClaudeFetcher
from commonplace._fetch._commands import fetch
from commonplace._fetch._helpers import FetchBlocked
from commonplace._import._claude import ClaudeImporter
from commonplace._wire import read_entries

ORG = "org-uuid-1"

SUMMARIES = [
    {"uuid": "c-old", "name": "Old", "updated_at": "2026-06-01T00:00:00Z"},
    {"uuid": "c-new", "name": "New", "updated_at": "2026-07-15T00:00:00Z"},
]

TEST_COOKIES = {"sessionKey": "sk-test", "lastActiveOrg": ORG}


def _utc(*args) -> datetime:
    return datetime(*args, tzinfo=UTC)


def _detail(uuid: str) -> dict:
    return {
        "uuid": uuid,
        "name": f"Chat {uuid}",
        "created_at": "2026-07-15T00:00:00Z",
        "updated_at": "2026-07-15T00:00:00Z",
        "chat_messages": [
            {
                "uuid": "m1",
                "sender": "human",
                "text": f"Hello from {uuid}",
                "created_at": "2026-07-15T00:00:00Z",
            },
            {
                "uuid": "m2",
                "sender": "assistant",
                "text": f"Hi from {uuid}",
                "created_at": "2026-07-15T00:00:01Z",
            },
        ],
    }


def _handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path == f"/api/organizations/{ORG}/chat_conversations":
        return httpx.Response(200, json=SUMMARIES)
    prefix = f"/api/organizations/{ORG}/chat_conversations/"
    if path.startswith(prefix):
        uuid = path[len(prefix) :]
        return httpx.Response(200, json=_detail(uuid))
    return httpx.Response(404)


def _make_fetcher(handler=_handler, cookies=TEST_COOKIES) -> ClaudeFetcher:
    return ClaudeFetcher(cookies=cookies, transport=httpx.MockTransport(handler))


def _read_wire(archive: Path) -> list[dict]:
    return list(read_entries(archive))


# ---------------------------------------------------------------------------
# Fetcher tests — cookies + transport injected via the constructor.
# ---------------------------------------------------------------------------


def test_fetch_returns_none_without_org(tmp_path):
    fetcher = ClaudeFetcher(cookies={"sessionKey": "sk"})
    assert fetcher.fetch(tmp_path, since=None) is None


def test_fetch_writes_raw_wire_only(tmp_path):
    """One entry per API call, in call order."""
    archive = _make_fetcher().fetch(tmp_path, since=None)
    assert archive is not None
    assert archive.name == "claude-wire.jsonl.gz"

    wire = _read_wire(archive)
    # 1 list call + 2 details for the two summaries.
    assert [e["endpoint"] for e in wire] == ["conversations", "conversation", "conversation"]
    assert json.loads(wire[0]["response"]) == SUMMARIES
    assert wire[1]["cid"] == "c-old"
    assert wire[2]["cid"] == "c-new"


def test_fetch_stores_response_bodies_verbatim(tmp_path):
    """The archive is what the server sent, byte for byte. Parsing and
    re-serialising would rewrite `1e5` as `100000.0`, `\\/` as `/` and
    `3.140` as `3.14`, so the artifact would no longer be evidence of what
    Anthropic actually returned."""
    raw_list = '[{"uuid": "c-new", "name": "Caf\\u00e9",  "updated_at": "2026-07-15T00:00:00Z", "n": 1e5}]'
    raw_detail = '{"uuid": "c-new", "name": "Caf\\u00e9", "created_at": "2026-07-15T00:00:00Z", "chat_messages": []}'

    def handler(request: httpx.Request) -> httpx.Response:
        headers = {"content-type": "application/json"}
        if request.url.path == f"/api/organizations/{ORG}/chat_conversations":
            return httpx.Response(200, content=raw_list, headers=headers)
        return httpx.Response(200, content=raw_detail, headers=headers)

    archive = _make_fetcher(handler=handler).fetch(tmp_path, since=None)
    assert archive is not None
    wire = _read_wire(archive)
    assert wire[0]["response"] == raw_list
    assert wire[1]["response"] == raw_detail


def test_fetch_records_the_request_id(tmp_path):
    """claude.ai returns a `request-id` on every response. It is the only
    handle by which a capture could be correlated against Anthropic's own
    records, and it is gone the moment the response is dropped."""

    def handler(request: httpx.Request) -> httpx.Response:
        response = _handler(request)
        response.headers["request-id"] = f"req_{request.url.path.rsplit('/', 1)[-1]}"
        return response

    archive = _make_fetcher(handler=handler).fetch(tmp_path, since=None)
    assert archive is not None
    wire = _read_wire(archive)
    assert [e["request_id"] for e in wire] == ["req_chat_conversations", "req_c-old", "req_c-new"]


def test_fetch_omits_request_id_when_the_response_has_none(tmp_path):
    """An absent key already says the header wasn't there; writing `null`
    would add nothing and is a reading the fetcher has no business making."""
    archive = _make_fetcher().fetch(tmp_path, since=None)
    assert archive is not None
    assert all("request_id" not in entry for entry in _read_wire(archive))


def test_fetch_end_to_end(tmp_path):
    archive = _make_fetcher().fetch(tmp_path, since=None)
    assert archive is not None
    assert ClaudeImporter().can_import(archive)
    assert len(ClaudeImporter().import_(archive)) == 2


def test_fetch_incremental_skips_seen(tmp_path):
    """Cursor at or after latest summary → nothing to fetch."""
    assert _make_fetcher().fetch(tmp_path, since=_utc(2026, 7, 15)) is None


def test_fetch_incremental_picks_up_newer(tmp_path):
    """Cursor between the two summaries → only the newer one."""
    archive = _make_fetcher().fetch(tmp_path, since=_utc(2026, 6, 15))
    assert archive is not None
    logs = ClaudeImporter().import_(archive)
    assert len(logs) == 1
    assert logs[0].metadata["uuid"] == "c-new"


def test_fetch_cursor_honours_offset(tmp_path):
    """A cursor of 00:30+01:00 is 23:30Z the previous day, so both
    conversations are newer than it."""
    cursor = datetime(2026, 6, 1, 0, 30, tzinfo=timezone(timedelta(hours=1)))
    archive = _make_fetcher().fetch(tmp_path, since=cursor)
    assert archive is not None
    uuids = {log.metadata["uuid"] for log in ClaudeImporter().import_(archive)}
    assert uuids == {"c-old", "c-new"}


def test_fetch_cursor_honours_subsecond_precision(tmp_path):
    """Claude stamps microseconds; half a second past the cursor is new."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == f"/api/organizations/{ORG}/chat_conversations":
            return httpx.Response(200, json=[{**SUMMARIES[1], "updated_at": "2026-07-15T00:00:00.500000Z"}])
        return _handler(request)

    archive = _make_fetcher(handler=handler).fetch(tmp_path, since=_utc(2026, 7, 15))
    assert archive is not None
    assert len(ClaudeImporter().import_(archive)) == 1


def test_fetch_command_dispatches(test_repo):
    """`commonplace fetch` runs configured fetchers and imports the result."""
    fetch(test_repo, fetchers=[_make_fetcher()], auto_index=False)

    chats = list((Path(test_repo.root) / "chats" / "claude").rglob("*.md"))
    assert len(chats) == 2


def test_fetch_raises_on_401(tmp_path):
    with pytest.raises(FetchBlocked):
        _make_fetcher(handler=lambda r: httpx.Response(401)).fetch(tmp_path, since=None)
