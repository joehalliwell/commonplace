"""Tests for the Gemini fetcher (and its paired importer)."""

import json
import re
from pathlib import Path

import httpx
import pytest

from commonplace._fetch._gemini import (
    GeminiFetcher,
    _extract_rpc_body,
    _ts_to_iso,
)
from commonplace._import._gemini_web import GeminiWebImporter

FIXTURES = Path(__file__).parent / "resources" / "gemini-samples"
LIST_CHATS_RAW = (FIXTURES / "list_chats.txt").read_text()
READ_CHAT_RAW = (FIXTURES / "read_chat.txt").read_text()

# An empty list_chats response (no rows, null cursor) — signals end-of-pagination.
EMPTY_LIST_CHATS = ')]}\'\n\n0\n[["wrb.fr","MaZiqc","[null,null,[]]",null,null,null,"generic"]]'


def _fake_app_page() -> str:
    """Minimal HTML with the three tokens the fetcher scrapes."""
    return '<html><script>{"SNlM0e":"AT-token-abc","cfb2h":"bl-xyz","FdrFJe":"-123"}</script></html>'


def _extract_payload_cursor(request: httpx.Request) -> str | None:
    """Pull the cursor (payload slot [1]) out of the batchexecute POST body."""
    from urllib.parse import parse_qs

    fields = parse_qs(request.content.decode())
    envelope = json.loads(fields["f.req"][0])
    inner = json.loads(envelope[0][0][1])
    return inner[1]  # payload[1] is the cursor for LIST_CHATS


def _handler(request: httpx.Request) -> httpx.Response:
    """Serve /app then batchexecute. LIST_CHATS returns the fixture on the
    first call per bucket, then an empty page on the second (to terminate)."""
    if request.url.path.endswith("/app"):
        return httpx.Response(200, text=_fake_app_page())
    if "batchexecute" in request.url.path:
        rpcids = request.url.params.get("rpcids", "")
        if rpcids == "MaZiqc":
            cursor = _extract_payload_cursor(request)
            # First call in a bucket: cursor is None → return fixture (which
            # contains a cursor). Second call: cursor is set → terminate.
            return httpx.Response(200, text=EMPTY_LIST_CHATS if cursor else LIST_CHATS_RAW)
        if rpcids == "hNvQHb":
            return httpx.Response(200, text=READ_CHAT_RAW)
    return httpx.Response(404)


@pytest.fixture
def mock_http(monkeypatch):
    transport = httpx.MockTransport(_handler)
    real_client = httpx.Client

    def factory(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr("commonplace._fetch._gemini.httpx.Client", factory)


@pytest.fixture
def stub_cookies(monkeypatch):
    monkeypatch.setattr(
        GeminiFetcher,
        "_read_cookies",
        lambda self: {"__Secure-1PSID": "psid", "__Secure-1PSIDTS": "psidts"},
    )


@pytest.fixture
def stub_cursor(monkeypatch):
    state = {"value": None}

    def setter(ts):
        state["value"] = ts

    monkeypatch.setattr(GeminiFetcher, "_last_import_time", lambda self, repo: state["value"])
    return setter


def test_ts_to_iso_truncates_nanos_to_micros():
    assert _ts_to_iso(1750141638, 548904000) == "2025-06-17T06:27:18.548904Z"


def test_extract_rpc_body_pulls_correct_wrb():
    body = _extract_rpc_body(READ_CHAT_RAW, "hNvQHb")
    assert isinstance(body, list)
    # body[0] is the turns list
    assert isinstance(body[0], list)


def test_extract_rpc_body_raises_on_missing():
    with pytest.raises(RuntimeError, match="No wrb.fr entry"):
        _extract_rpc_body(READ_CHAT_RAW, "unknown-rpc")


def test_extract_rpc_body_raises_on_bad_preamble():
    with pytest.raises(RuntimeError, match="preamble"):
        _extract_rpc_body("not-a-real-response", "MaZiqc")


def test_fetch_returns_none_without_session(monkeypatch, test_repo, tmp_path):
    monkeypatch.setattr(GeminiFetcher, "_read_cookies", lambda self: {})
    assert GeminiFetcher().fetch(tmp_path, test_repo) is None


def test_fetch_end_to_end(mock_http, stub_cookies, stub_cursor, test_repo, tmp_path):
    """Full path: scrape tokens, list, read, produce an importable JSON archive."""
    archive = GeminiFetcher().fetch(tmp_path, test_repo)
    assert archive is not None
    assert archive.name == "gemini-fetch.json"

    data = json.loads(archive.read_text())
    # Mock returns the 5-chat fixture for both pinned + unpinned buckets → 10 chats.
    assert len(data) == 10
    for chat in data:
        assert chat["cid"].startswith("c_")
        assert re.match(r"CHAT_TITLE_\d", chat["title"])
        assert chat["gem_name"] == "GEM_NAME"
        assert len(chat["rounds"]) == 3
        # Rounds should be chronological (oldest first) after reversal.
        timestamps = [r["timestamp"] for r in chat["rounds"]]
        assert timestamps == sorted(timestamps), "rounds must be chronological"


def test_fetch_extracts_per_turn_timestamps(mock_http, stub_cookies, stub_cursor, test_repo, tmp_path):
    archive = GeminiFetcher().fetch(tmp_path, test_repo)
    data = json.loads(archive.read_text())
    rounds = data[0]["rounds"]
    # The three timestamps in the fixture (chronological after reversal):
    assert [r["timestamp"] for r in rounds] == [
        "2025-06-17T06:01:53.371626Z",
        "2025-06-17T06:04:32.191904Z",
        "2025-06-17T06:27:18.548904Z",
    ]
    # Each round has both user + model text
    assert rounds[0]["user_text"] == "USER_TEXT_2"
    assert rounds[0]["model_text"] == "MODEL_TEXT_2_0"
    assert rounds[0]["model_thoughts"] == "MODEL_THOUGHTS_2_0"
    assert rounds[0]["language"] == "en"


def test_fetch_incremental_skips_seen(mock_http, stub_cookies, stub_cursor, test_repo, tmp_path):
    """A cursor >= all summaries' updated_at → nothing to fetch."""
    stub_cursor("2030-01-01T00:00:00Z")
    assert GeminiFetcher().fetch(tmp_path, test_repo) is None


def test_importer_recognizes_fetcher_output(tmp_path):
    """GeminiWebImporter.can_import must accept the fetcher's JSON."""
    path = tmp_path / "gemini-fetch.json"
    path.write_text(json.dumps([{"cid": "c_abc", "title": "t", "rounds": []}]))
    assert GeminiWebImporter().can_import(path)


def test_importer_rejects_arbitrary_json(tmp_path):
    path = tmp_path / "other.json"
    path.write_text(json.dumps({"not": "a chat list"}))
    assert not GeminiWebImporter().can_import(path)


def test_importer_produces_events_with_shared_timestamps(mock_http, stub_cookies, stub_cursor, test_repo, tmp_path):
    """User and model messages in a round share the wire timestamp."""
    archive = GeminiFetcher().fetch(tmp_path, test_repo)
    logs = GeminiWebImporter().import_(archive)
    assert len(logs) == 10
    log = logs[0]
    assert log.source == "gemini"
    assert log.metadata["uuid"].startswith("c_")
    assert log.metadata["gem"] == "GEM_NAME"
    # 3 rounds × 2 messages
    assert len(log.events) == 6
    # first user + model share timestamp
    assert log.events[0].created == log.events[1].created


def test_importer_carries_thoughts_and_language_metadata(mock_http, stub_cookies, stub_cursor, test_repo, tmp_path):
    archive = GeminiFetcher().fetch(tmp_path, test_repo)
    logs = GeminiWebImporter().import_(archive)
    # events[1] is the earliest model message. In the wire the fixture's turns
    # are newest-first: turn[0], turn[1], turn[2]. After chronological reversal,
    # the earliest round corresponds to wire turn[2] → MODEL_THOUGHTS_2_0.
    model_msg = logs[0].events[1]
    assert model_msg.metadata["language"] == "en"
    assert model_msg.metadata["thoughts"] == "MODEL_THOUGHTS_2_0"
    assert model_msg.metadata["rcid"].startswith("rc_")


def test_fetch_retries_transient_5xx(monkeypatch, stub_cookies, stub_cursor, test_repo, tmp_path):
    monkeypatch.setattr("commonplace._fetch._gemini.time.sleep", lambda _: None)

    calls: dict[str, int] = {}

    def flaky(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        calls[path] = calls.get(path, 0) + 1
        if path.endswith("/app"):
            return httpx.Response(200, text=_fake_app_page())
        # First batchexecute request 503s; subsequent succeed.
        if "batchexecute" in path and calls[path] == 1:
            return httpx.Response(503)
        return _handler(request)

    transport = httpx.MockTransport(flaky)
    real_client = httpx.Client

    def factory(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr("commonplace._fetch._gemini.httpx.Client", factory)

    archive = GeminiFetcher().fetch(tmp_path, test_repo)
    assert archive is not None


def test_fetch_raises_on_403(monkeypatch, stub_cookies, stub_cursor, test_repo, tmp_path):
    def handler(request):
        if request.url.path.endswith("/app"):
            return httpx.Response(200, text=_fake_app_page())
        return httpx.Response(403)

    transport = httpx.MockTransport(handler)
    real_client = httpx.Client

    def factory(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr("commonplace._fetch._gemini.httpx.Client", factory)

    with pytest.raises(RuntimeError, match="session rejected"):
        GeminiFetcher().fetch(tmp_path, test_repo)


def test_read_chat_skips_null_body(monkeypatch, stub_cookies, stub_cursor, test_repo, tmp_path, caplog):
    """Per-chat access glitches (wrb.fr body = null) log a warning and yield
    an empty-turns chat, rather than aborting the batch."""
    import logging

    null_body_response = ')]}\'\n\n0\n[["wrb.fr","hNvQHb",null,null,null,null,"generic"]]'

    def handler(request):
        if request.url.path.endswith("/app"):
            return httpx.Response(200, text=_fake_app_page())
        if "batchexecute" in request.url.path:
            rpcids = request.url.params.get("rpcids", "")
            if rpcids == "MaZiqc":
                cursor = _extract_payload_cursor(request)
                return httpx.Response(200, text=EMPTY_LIST_CHATS if cursor else LIST_CHATS_RAW)
            if rpcids == "hNvQHb":
                return httpx.Response(200, text=null_body_response)
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    real_client = httpx.Client

    def factory(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr("commonplace._fetch._gemini.httpx.Client", factory)

    with caplog.at_level(logging.WARNING, logger="commonplace"):
        archive = GeminiFetcher().fetch(tmp_path, test_repo)
    assert archive is not None
    data = json.loads(archive.read_text())
    assert all(chat["rounds"] == [] for chat in data)
    assert any("Empty response" in r.message for r in caplog.records)


def test_read_session_tokens_raises_on_missing_html(monkeypatch, stub_cookies, test_repo, tmp_path):
    def handler(request):
        if request.url.path.endswith("/app"):
            return httpx.Response(200, text="<html>no tokens here</html>")
        return httpx.Response(200, text=")]}'\n\n0\n[]")

    transport = httpx.MockTransport(handler)
    real_client = httpx.Client

    def factory(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr("commonplace._fetch._gemini.httpx.Client", factory)
    monkeypatch.setattr(GeminiFetcher, "_last_import_time", lambda self, repo: None)

    with pytest.raises(RuntimeError, match="access token"):
        GeminiFetcher().fetch(tmp_path, test_repo)
