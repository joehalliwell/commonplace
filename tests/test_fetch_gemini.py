"""Tests for the Gemini fetcher (and its paired importer)."""

import gzip
import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

from commonplace._fetch._gemini import GeminiFetcher
from commonplace._import._gemini import GeminiImporter, _extract_rpc_body, _ts_to_iso
from commonplace._wire import read_entries

FIXTURES = Path(__file__).parent / "resources" / "gemini-samples"
LIST_CHATS_RAW = (FIXTURES / "list_chats.txt").read_text()
READ_CHAT_RAW = (FIXTURES / "read_chat.txt").read_text()

# An empty list_chats response (no rows, null cursor) — signals end-of-pagination.
EMPTY_LIST_CHATS = ')]}\'\n\n0\n[["wrb.fr","MaZiqc","[null,null,[]]",null,null,null,"generic"]]'

TEST_COOKIES = {"__Secure-1PSID": "psid", "__Secure-1PSIDTS": "psidts"}


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
            return httpx.Response(200, text=EMPTY_LIST_CHATS if cursor else LIST_CHATS_RAW)
        if rpcids == "hNvQHb":
            return httpx.Response(200, text=READ_CHAT_RAW)
    return httpx.Response(404)


def _make_fetcher(handler=_handler, cookies=TEST_COOKIES) -> GeminiFetcher:
    return GeminiFetcher(cookies=cookies, transport=httpx.MockTransport(handler))


def _read_wire(archive: Path) -> list[dict]:
    return list(read_entries(archive))


# ---------------------------------------------------------------------------
# Unit tests on shared wire helpers.
# ---------------------------------------------------------------------------


def test_ts_to_iso_truncates_nanos_to_micros():
    assert _ts_to_iso(1750141638, 548904000) == "2025-06-17T06:27:18.548904Z"


def test_extract_rpc_body_pulls_correct_wrb():
    body = _extract_rpc_body(READ_CHAT_RAW, "hNvQHb")
    assert isinstance(body, list)
    assert isinstance(body[0], list)


def test_extract_rpc_body_raises_on_missing():
    with pytest.raises(RuntimeError, match="No wrb.fr entry"):
        _extract_rpc_body(READ_CHAT_RAW, "unknown-rpc")


def test_extract_rpc_body_raises_on_bad_preamble():
    with pytest.raises(RuntimeError, match="preamble"):
        _extract_rpc_body("not-a-real-response", "MaZiqc")


# ---------------------------------------------------------------------------
# Fetcher tests — cookies + transport injected via the constructor.
# ---------------------------------------------------------------------------


def test_fetch_returns_none_without_session(tmp_path):
    assert GeminiFetcher(cookies={}).fetch(tmp_path, since=None) is None


def test_fetch_writes_raw_wire_only(tmp_path):
    """The fetcher's artifact is a JSONL of raw `batchexecute` responses —
    no invented intermediate format."""
    archive = _make_fetcher().fetch(tmp_path, since=None)
    assert archive is not None
    assert archive.name == "gemini-wire.jsonl.gz"

    wire = _read_wire(archive)
    # 2 list_chats buckets × 2 pages each (real + terminating empty) = 4
    # plus 5 read_chat calls × 2 buckets = 10 → 14 entries.
    list_calls = [e for e in wire if e["rpc"] == "MaZiqc"]
    read_calls = [e for e in wire if e["rpc"] == "hNvQHb"]
    assert len(list_calls) == 4
    assert len(read_calls) == 10
    for entry in wire:
        assert entry["response"].startswith(")]}'\n"), "raw batchexecute preamble preserved"
        assert set(entry.keys()) == {"rpc", "payload", "response"}


def test_fetch_incremental_skips_seen(tmp_path):
    """A cursor >= all summaries' updated_at → nothing to fetch."""
    assert _make_fetcher().fetch(tmp_path, since=datetime(2030, 1, 1, tzinfo=UTC)) is None


def test_fetch_cursor_honours_offset(tmp_path):
    """The same instant spelled as +01:00 behaves like its UTC spelling."""
    zulu = datetime(2030, 1, 1, 0, 0, tzinfo=UTC)
    bst = datetime(2030, 1, 1, 1, 0, tzinfo=timezone(timedelta(hours=1)))
    assert _make_fetcher().fetch(tmp_path, since=zulu) is None
    assert _make_fetcher().fetch(tmp_path, since=bst) is None


def test_fetch_retries_transient_5xx(no_retry_sleep, tmp_path):
    calls: dict[str, int] = {}

    def flaky(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        calls[path] = calls.get(path, 0) + 1
        if path.endswith("/app"):
            return httpx.Response(200, text=_fake_app_page())
        if "batchexecute" in path and calls[path] == 1:
            return httpx.Response(503)
        return _handler(request)

    archive = _make_fetcher(handler=flaky).fetch(tmp_path, since=None)
    assert archive is not None


def test_fetch_raises_on_403(tmp_path):
    def handler(request):
        if request.url.path.endswith("/app"):
            return httpx.Response(200, text=_fake_app_page())
        return httpx.Response(403)

    with pytest.raises(RuntimeError, match="session rejected"):
        _make_fetcher(handler=handler).fetch(tmp_path, since=None)


def test_read_session_tokens_raises_on_missing_html(tmp_path):
    def handler(request):
        if request.url.path.endswith("/app"):
            return httpx.Response(200, text="<html>no tokens here</html>")
        return httpx.Response(200, text=")]}'\n\n0\n[]")

    with pytest.raises(RuntimeError, match="access token"):
        _make_fetcher(handler=handler).fetch(tmp_path, since=None)


# ---------------------------------------------------------------------------
# Importer tests.
# ---------------------------------------------------------------------------


def test_importer_recognizes_wire_jsonl_gz(tmp_path):
    path = tmp_path / "wire.jsonl.gz"
    with gzip.open(path, "wt", encoding="utf-8") as f:
        f.write(json.dumps({"rpc": "MaZiqc", "payload": [], "response": ")]}'\n"}) + "\n")
    assert GeminiImporter().can_import(path)


def test_importer_rejects_arbitrary_gz(tmp_path):
    path = tmp_path / "other.jsonl.gz"
    with gzip.open(path, "wt", encoding="utf-8") as f:
        f.write(json.dumps({"not": "a wire log"}) + "\n")
    assert not GeminiImporter().can_import(path)


def test_importer_rejects_non_gz(tmp_path):
    path = tmp_path / "chats.json"
    path.write_text("[]")
    assert not GeminiImporter().can_import(path)


def test_importer_rejects_uncompressed_jsonl(tmp_path):
    """The archive is always gzipped; a bare .jsonl isn't ours."""
    path = tmp_path / "wire.jsonl"
    path.write_text(json.dumps({"rpc": "MaZiqc", "payload": [], "response": ""}) + "\n")
    assert not GeminiImporter().can_import(path)


def test_importer_reconstructs_events_from_wire(tmp_path):
    """The importer reads raw responses and produces EventLogs with per-turn
    timestamps drawn from the wire."""
    archive = _make_fetcher().fetch(tmp_path, since=None)
    logs = GeminiImporter().import_(archive)

    # 5 chats × 2 buckets (mock returns fixture for both pinned + unpinned) = 10.
    assert len(logs) == 10
    log = logs[0]
    assert log.source == "gemini"
    assert log.metadata["uuid"].startswith("c_")
    assert log.metadata["gem"] == "GEM_NAME"
    assert log.title.startswith("CHAT_TITLE_")
    # 3 rounds × 2 messages
    assert len(log.events) == 6
    # first user + model share timestamp
    assert log.events[0].created == log.events[1].created
    # Chronological order after wire-reversal.
    times = [e.created for e in log.events]
    assert times == sorted(times)


def test_importer_carries_thoughts_metadata(tmp_path):
    archive = _make_fetcher().fetch(tmp_path, since=None)
    logs = GeminiImporter().import_(archive)
    # events[1] is the earliest model message. Wire turns are newest-first in
    # the fixture; after chronological reversal the earliest round is wire
    # turn[2] → MODEL_THOUGHTS_2_0.
    model_msg = logs[0].events[1]
    assert model_msg.metadata == {"thoughts": "MODEL_THOUGHTS_2_0"}
    # User messages carry no metadata — rid/rcid/language are noise.
    assert logs[0].events[0].metadata == {}


def test_importer_extracts_per_turn_timestamps_from_wire(tmp_path):
    archive = _make_fetcher().fetch(tmp_path, since=None)
    logs = GeminiImporter().import_(archive)
    # The three per-round timestamps in the fixture (chronological after reversal):
    times = [e.created.isoformat().replace("+00:00", "Z") for e in logs[0].events[::2]]  # user messages only
    assert times == [
        "2025-06-17T06:01:53.371626Z",
        "2025-06-17T06:04:32.191904Z",
        "2025-06-17T06:27:18.548904Z",
    ]


def test_importer_handles_null_body_with_warning(tmp_path, caplog):
    """Per-chat access glitches (wrb.fr body = null) log a warning and yield
    an EventLog with no events, rather than aborting the batch."""
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

    archive = _make_fetcher(handler=handler).fetch(tmp_path, since=None)
    assert archive is not None
    with caplog.at_level(logging.WARNING, logger="commonplace"):
        logs = GeminiImporter().import_(archive)
    assert all(log.events == [] for log in logs)
    assert any("Empty response" in r.message for r in caplog.records)
