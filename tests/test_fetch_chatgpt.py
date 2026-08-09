"""Tests for the ChatGPT importers (and, below, the fetcher)."""

import json
from datetime import UTC, datetime
from pathlib import Path
from zipfile import ZipFile

import httpx
import pytest

from commonplace._fetch._chatgpt import ChatGptFetcher
from commonplace._fetch._helpers import FetchBlocked
from commonplace._import._chatgpt import ChatGptImporter, ChatGptWireImporter
from commonplace._import._claude import ClaudeImporter
from commonplace._wire import WIRE_VERSION, read_entries, read_header, write_archive


def _msg(node_id: str, role: str, text: str, **overrides) -> dict:
    message = {
        "id": node_id,
        "author": {"role": role, "name": None, "metadata": {}},
        "create_time": 1785132346.0,
        "content": {"content_type": "text", "parts": [text]},
        "recipient": "all",
        "metadata": {},
    }
    message.update(overrides)
    return message


def _conversation(mapping: dict, current_node: str | None = None, **overrides) -> dict:
    conversation = {
        "id": "conv-1",
        "title": "Test",
        "create_time": 1785132346.0,
        "mapping": mapping,
        "current_node": current_node,
    }
    conversation.update(overrides)
    return conversation


def _linear(*messages: dict) -> tuple[dict, str]:
    """Build a root + chain of message nodes. Returns (mapping, leaf_id)."""
    mapping: dict[str, dict] = {"root": {"id": "root", "message": None, "parent": None, "children": []}}
    prev = "root"
    for message in messages:
        node_id = message["id"]
        mapping[prev]["children"].append(node_id)
        mapping[node_id] = {"id": node_id, "message": message, "parent": prev, "children": []}
        prev = node_id
    return mapping, prev


def _zip(tmp_path: Path, conversations: list[dict]) -> Path:
    path = tmp_path / "chatgpt-export.zip"
    with ZipFile(path, "w") as zf:
        zf.writestr("conversations.json", json.dumps(conversations))
        zf.writestr("user.json", "{}")
    return path


def _import(tmp_path: Path, conversation: dict):
    return ChatGptImporter().import_(_zip(tmp_path, [conversation]))[0]


def test_import_reads_a_linear_thread(tmp_path):
    mapping, leaf = _linear(_msg("a", "user", "hello"), _msg("b", "assistant", "hi back"))
    log = _import(tmp_path, _conversation(mapping, current_node=leaf))

    assert [e.content for e in log.events] == ["hello", "hi back"]


def test_import_follows_the_branch_ending_at_current_node(tmp_path):
    """A regenerate forks the mapping. `children[0]` is the abandoned branch;
    `current_node` names the leaf of the live one."""
    mapping, _ = _linear(_msg("a", "user", "hello"))
    for node_id, text in (("abandoned", "first attempt"), ("kept", "second attempt")):
        mapping["a"]["children"].append(node_id)
        mapping[node_id] = {
            "id": node_id,
            "message": _msg(node_id, "assistant", text),
            "parent": "a",
            "children": [],
        }

    log = _import(tmp_path, _conversation(mapping, current_node="kept"))

    assert [e.content for e in log.events] == ["hello", "second attempt"]


def test_import_falls_back_to_first_child_without_current_node(tmp_path):
    mapping, _ = _linear(_msg("a", "user", "hello"), _msg("b", "assistant", "hi back"))
    log = _import(tmp_path, _conversation(mapping, current_node=None))

    assert [e.content for e in log.events] == ["hello", "hi back"]


def test_import_skips_tool_traffic(tmp_path):
    """`recipient` other than "all" addresses a tool, not the conversation."""
    mapping, leaf = _linear(
        _msg("a", "user", "search for badgers"),
        _msg("b", "assistant", '{"query": "badgers"}', recipient="web"),
        _msg("c", "assistant", "Badgers are mustelids."),
    )
    log = _import(tmp_path, _conversation(mapping, current_node=leaf))

    assert [e.content for e in log.events] == ["search for badgers", "Badgers are mustelids."]


def test_import_skips_visually_hidden_messages(tmp_path):
    """The flag lives on the message's metadata, not the node's."""
    mapping, leaf = _linear(
        _msg("a", "user", "context injected by the client", metadata={"is_visually_hidden_from_conversation": True}),
        _msg("b", "user", "hello"),
        _msg("c", "assistant", "hi back"),
    )
    log = _import(tmp_path, _conversation(mapping, current_node=leaf))

    assert [e.content for e in log.events] == ["hello", "hi back"]


def test_import_skips_non_text_content(tmp_path):
    """`code` blocks carry `text`/`language` and no `parts`."""
    mapping, leaf = _linear(
        _msg("a", "user", "hello"),
        _msg(
            "b",
            "assistant",
            "",
            content={"content_type": "code", "language": "unknown", "text": "search(...)"},
            recipient="all",
        ),
        _msg("c", "assistant", "hi back"),
    )
    log = _import(tmp_path, _conversation(mapping, current_node=leaf))

    assert [e.content for e in log.events] == ["hello", "hi back"]


def test_import_uses_conversation_id_when_id_absent(tmp_path):
    """Fetched detail responses carry `conversation_id`; exports carry `id`."""
    mapping, leaf = _linear(_msg("a", "user", "hello"))
    conversation = _conversation(mapping, current_node=leaf)
    del conversation["id"]
    conversation["conversation_id"] = "from-wire"

    log = _import(tmp_path, conversation)

    assert log.metadata["id"] == "from-wire"


# ---------------------------------------------------------------------------
# Fetcher tests — cookies + transport injected via the constructor.
# ---------------------------------------------------------------------------

SESSION_COOKIES = {
    # NextAuth chunks the session token past ~4KB.
    "__Secure-next-auth.session-token.0": "chunk0",
    "__Secure-next-auth.session-token.1": "chunk1",
    "cf_clearance": "cf",
}

# The list endpoint spells timestamps as ISO strings; detail uses epoch floats.
LIST_ITEMS = [
    {"id": "c-new", "title": "New", "update_time": "2026-07-28T00:00:00.000000Z"},
    {"id": "c-old", "title": "Old", "update_time": "2026-06-01T00:00:00.000000Z"},
]


def _detail_body(cid: str) -> str:
    mapping, leaf = _linear(_msg("a", "user", f"hello {cid}"), _msg("b", "assistant", f"hi from {cid}"))
    conversation = _conversation(mapping, current_node=leaf, conversation_id=cid, title=f"Chat {cid}")
    del conversation["id"]
    return json.dumps(conversation)


def _handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path == "/api/auth/session":
        return httpx.Response(200, json={"accessToken": "jwt-token", "user": {}})
    if path == "/backend-api/conversations":
        offset = int(request.url.params.get("offset", 0))
        page = LIST_ITEMS[offset : offset + 100]
        return httpx.Response(200, json={"items": page, "total": len(LIST_ITEMS), "limit": 100, "offset": offset})
    if path.startswith("/backend-api/conversation/"):
        return httpx.Response(200, content=_detail_body(path.rsplit("/", 1)[-1]))
    return httpx.Response(404)


@pytest.fixture(autouse=True)
def no_request_pacing(monkeypatch):
    """The fetcher paces requests to stay under Cloudflare's bot check; tests
    exercise the logic, not the throttle."""
    monkeypatch.setattr(ChatGptFetcher, "request_interval", 0)


def _make_fetcher(handler=_handler, cookies=SESSION_COOKIES) -> ChatGptFetcher:
    return ChatGptFetcher(cookies=cookies, transport=httpx.MockTransport(handler))


def test_fetch_returns_none_without_session_cookie(tmp_path):
    assert ChatGptFetcher(cookies={"cf_clearance": "cf"}).fetch(tmp_path, since=None) is None


def test_fetch_accepts_chunked_session_cookie(tmp_path):
    """The token arrives as `.0`/`.1`; httpx sends both and the server rejoins."""
    archive = _make_fetcher().fetch(tmp_path, since=None)
    assert archive is not None


def test_fetch_writes_a_chatgpt_wire_archive(tmp_path):
    archive = _make_fetcher().fetch(tmp_path, since=None)
    assert archive is not None
    assert archive.name == "chatgpt-wire.jsonl.gz"
    header = read_header(archive)
    assert (header.source, header.version) == ("chatgpt", WIRE_VERSION)

    entries = list(read_entries(archive))
    assert [e["endpoint"] for e in entries] == ["conversations", "conversation", "conversation"]
    assert [e["cid"] for e in entries[1:]] == ["c-new", "c-old"]


def test_fetch_stores_response_bodies_verbatim(tmp_path):
    raw = '{"items": [{"id": "c-new",  "title": "Caf\\u00e9", "update_time": "2026-07-28T00:00:00Z"}], "total": 1}'

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/backend-api/conversations":
            return httpx.Response(200, content=raw, headers={"content-type": "application/json"})
        return _handler(request)

    archive = _make_fetcher(handler=handler).fetch(tmp_path, since=None)
    assert archive is not None
    assert next(iter(read_entries(archive)))["response"] == raw


def test_fetch_paginates(tmp_path):
    """`total` exceeds one page, so the fetcher walks offsets until exhausted."""
    items = [{"id": f"c{i}", "title": str(i), "update_time": "2026-07-28T00:00:00.000000Z"} for i in range(250)]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/backend-api/conversations":
            offset = int(request.url.params.get("offset", 0))
            limit = int(request.url.params.get("limit", 100))
            page = items[offset : offset + limit]
            return httpx.Response(200, json={"items": page, "total": len(items), "limit": limit, "offset": offset})
        return _handler(request)

    archive = _make_fetcher(handler=handler).fetch(tmp_path, since=None)
    assert archive is not None
    entries = list(read_entries(archive))
    assert len([e for e in entries if e["endpoint"] == "conversations"]) == 3  # 100 + 100 + 50
    assert len([e for e in entries if e["endpoint"] == "conversation"]) == 250


def test_fetch_stops_paging_once_past_the_cursor(tmp_path):
    """Listing is ordered by update_time desc, so the first stale item ends it."""
    requested: list[int] = []
    items = [
        {"id": f"c{i}", "title": str(i), "update_time": f"2026-07-{28 - i:02d}T00:00:00.000000Z"} for i in range(150)
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/backend-api/conversations":
            offset = int(request.url.params.get("offset", 0))
            requested.append(offset)
            page = items[offset : offset + 100]
            return httpx.Response(200, json={"items": page, "total": len(items), "limit": 100, "offset": offset})
        return _handler(request)

    archive = _make_fetcher(handler=handler).fetch(tmp_path, since=datetime(2026, 7, 26, tzinfo=UTC))
    assert archive is not None
    assert requested == [0], "should not request a second page once a stale item is seen"
    assert len([e for e in read_entries(archive) if e["endpoint"] == "conversation"]) == 2


def test_fetch_returns_none_when_nothing_is_new(tmp_path):
    assert _make_fetcher().fetch(tmp_path, since=datetime(2026, 7, 29, tzinfo=UTC)) is None


def test_fetch_raises_on_401(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/auth/session":
            return httpx.Response(200, json={"accessToken": "jwt-token", "user": {}})
        return httpx.Response(401)

    with pytest.raises(FetchBlocked):
        _make_fetcher(handler=handler).fetch(tmp_path, since=None)


def test_fetch_raises_when_session_has_no_access_token(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"user": {}})

    with pytest.raises(RuntimeError, match="access token"):
        _make_fetcher(handler=handler).fetch(tmp_path, since=None)


def test_fetch_sends_bearer_token(tmp_path):
    seen: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path != "/api/auth/session":
            seen.append(request.headers.get("authorization"))
        return _handler(request)

    _make_fetcher(handler=handler).fetch(tmp_path, since=None)
    assert seen and all(h == "Bearer jwt-token" for h in seen)


def test_fetch_retries_transient_5xx(no_retry_sleep, tmp_path):
    calls: dict[str, int] = {}

    def flaky(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        calls[path] = calls.get(path, 0) + 1
        if path.startswith("/backend-api/conversation/") and calls[path] == 1:
            return httpx.Response(503)
        return _handler(request)

    archive = _make_fetcher(handler=flaky).fetch(tmp_path, since=None)
    assert archive is not None
    assert len(ChatGptWireImporter().import_(archive)) == 2


# ---------------------------------------------------------------------------
# Wire importer.
# ---------------------------------------------------------------------------


def test_wire_importer_claims_only_its_own_archives(tmp_path):
    chatgpt = write_archive(tmp_path / "chatgpt-wire.jsonl.gz", "chatgpt", [])
    claude = write_archive(tmp_path / "claude-wire.jsonl.gz", "claude", [])

    assert ChatGptWireImporter().can_import(chatgpt)
    assert not ChatGptWireImporter().can_import(claude)
    assert not ClaudeImporter().can_import(chatgpt)


def test_wire_importer_reads_fetched_conversations(tmp_path):
    archive = _make_fetcher().fetch(tmp_path, since=None)
    assert archive is not None

    logs = ChatGptWireImporter().import_(archive)
    assert {log.metadata["id"] for log in logs} == {"c-new", "c-old"}
    assert [e.content for e in logs[0].events] == ["hello c-new", "hi from c-new"]
    assert all(log.source == "chatgpt" for log in logs)


def test_wire_importer_reads_epoch_timestamps(tmp_path):
    """Detail responses date conversations with epoch floats, not ISO strings."""
    archive = _make_fetcher().fetch(tmp_path, since=None)
    assert archive is not None

    log = ChatGptWireImporter().import_(archive)[0]
    assert log.created == datetime.fromtimestamp(1785132346.0, tz=UTC)


def test_fetch_paginates_when_total_under_reports(tmp_path):
    """`total` is not a count — the live API reports `total: 4` when asked for
    3 of 90 conversations. Paging must terminate on a short page instead."""
    items = [{"id": f"c{i}", "title": str(i), "update_time": "2026-07-28T00:00:00.000000Z"} for i in range(150)]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/backend-api/conversations":
            offset = int(request.url.params.get("offset", 0))
            limit = int(request.url.params.get("limit", 100))
            page = items[offset : offset + limit]
            understated = len(page) + (1 if offset + limit < len(items) else 0)
            return httpx.Response(200, json={"items": page, "total": understated, "limit": limit, "offset": offset})
        return _handler(request)

    archive = _make_fetcher(handler=handler).fetch(tmp_path, since=None)
    assert archive is not None
    assert len([e for e in read_entries(archive) if e["endpoint"] == "conversation"]) == 150


def _challenge_handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        403,
        content="<html><body>Just a moment...</body></html>",
        headers={"server": "cloudflare", "content-type": "text/html; charset=utf-8"},
    )


def test_fetch_distinguishes_a_bot_challenge_from_a_dead_session(tmp_path):
    """A 403 HTML page from Cloudflare is a bot check, not an expired session —
    logging in again does nothing, so the message must not suggest it."""
    with pytest.raises(FetchBlocked, match="bot challenge"):
        _make_fetcher(handler=_challenge_handler).fetch(tmp_path, since=None)


def test_bot_challenge_message_says_what_to_do(tmp_path):
    """The message is the whole remediation — the CLI prints it without a
    traceback, so anything the user needs has to be in here."""
    with pytest.raises(FetchBlocked) as excinfo:
        _make_fetcher(handler=_challenge_handler).fetch(tmp_path, since=None)

    message = str(excinfo.value)
    assert "https://chatgpt.com" in message, "where to go"
    assert "User-Agent" in message and "COMMONPLACE_UA" in message, "the likeliest cause and its fix"
    assert "re-run" in message.lower(), "what to do after"
    assert "Nothing was imported" in message, "whether the failed run cost anything"


def test_fetch_sends_accept_language(tmp_path):
    """Cloudflare 403s a Chrome User-Agent with no Accept-Language: no real
    browser omits it, so its absence reads as a bot."""
    seen: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("accept-language"))
        return _handler(request)

    _make_fetcher(handler=handler).fetch(tmp_path, since=None)

    assert seen and all(lang for lang in seen)


def test_fetch_uses_the_configured_user_agent(tmp_path):
    seen: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("user-agent"))
        return _handler(request)

    ChatGptFetcher(cookies=SESSION_COOKIES, transport=httpx.MockTransport(handler), ua="Custom/1.0").fetch(
        tmp_path, since=None
    )

    assert seen and all(ua == "Custom/1.0" for ua in seen)


def test_fetch_paces_requests(monkeypatch, tmp_path):
    """Requests are spaced; without this a full backfill trips Cloudflare."""
    monkeypatch.setattr(ChatGptFetcher, "request_interval", 10.0)
    slept: list[float] = []
    monkeypatch.setattr("commonplace._fetch._helpers.time.sleep", lambda s: slept.append(s))

    _make_fetcher().fetch(tmp_path, since=None)

    # 1 session + 1 list + 2 details = 4 requests, so 3 gaps.
    assert len(slept) == 3
    assert all(0 < s <= 10.0 for s in slept)


def test_fetch_widens_pacing_after_a_429(no_retry_sleep, tmp_path):
    """A 429 is the polite signal. Retrying alone forgets it happened; the
    remaining requests should stay slower."""
    fetcher = _make_fetcher(handler=_throttle_once_then_ok())
    before = fetcher._pacer.interval

    archive = fetcher.fetch(tmp_path, since=None)

    assert archive is not None
    assert fetcher._pacer.interval > before


def _throttle_once_then_ok():
    seen: set[str] = set()

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.startswith("/backend-api/conversation/") and path not in seen:
            seen.add(path)
            return httpx.Response(429)
        return _handler(request)

    return handler
