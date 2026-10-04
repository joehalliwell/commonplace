"""Tests for mirroring Gemini's saved info into `memory/gemini/`: fetcher, importer, and the path between."""

import json
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

import httpx
import pytest

from commonplace._fetch._commands import fetch
from commonplace._fetch._gemini_memory import GeminiMemoryFetcher
from commonplace._import._commands import autodetect_importer, landing_tree
from commonplace._import._gemini_memory import GeminiMemoryImporter
from commonplace._utils import load_frontmatter
from commonplace._wire import read_entries, read_header, write_archive
from tests.porcelain import git

EXAMPLE = Path(__file__).parent / "resources" / "wire" / "gemini-memory-v3.jsonl.gz"
SAVED_INFO = PurePosixPath("saved-info.md")

TEST_COOKIES = {"__Secure-1PSID": "psid", "__Secure-1PSIDTS": "psidts"}
APP_PAGE = '<html><script>{"SNlM0e":"AT-token-abc","cfb2h":"bl-xyz","FdrFJe":"-123"}</script></html>'


def _item(text: str, created: int, updated: int) -> list:
    return [f"id-{text}", text, [created, 0], None, [updated, 0], None, None, None, None, 1, 5]


def _response(items: list | None) -> str:
    """A batchexecute response carrying `items`, or a null body when `items` is None."""
    body = None if items is None else json.dumps([items, "dG9rZW4="])
    return ")]}'\n\n0\n" + json.dumps([["wrb.fr", "ZKcapf", body, None, None, None, "generic"]])


def _archive(tmp_path: Path, items: list | None) -> Path:
    entries = [{"rpc": "ZKcapf", "payload": [], "response": _response(items)}]
    return write_archive(tmp_path / "gemini-memory-wire.jsonl.gz", "gemini-memory", entries)


class FakeGemini:
    """Serves the /app page and the saved-info RPC, recording each batchexecute request."""

    def __init__(self, items: list | None = None):
        self.response = next(read_entries(EXAMPLE))["response"] if items is None else _response(items)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/app"):
            return httpx.Response(200, text=APP_PAGE)
        if "batchexecute" in request.url.path and request.url.params["rpcids"] == "ZKcapf":
            self.requests.append(request)
            return httpx.Response(200, text=self.response)
        return httpx.Response(404)

    def fetcher(self, cookies=TEST_COOKIES) -> GeminiMemoryFetcher:
        return GeminiMemoryFetcher(cookies=cookies, transport=httpx.MockTransport(self))


def _blobs(repo) -> set[Path]:
    return set((repo.root / ".commonplace" / "blobs").glob("*/*"))


# ---------------------------------------------------------------------------
# Importer
# ---------------------------------------------------------------------------


def test_snapshot_example_archive_lists_items_oldest_first():
    """Ordered by creation, so an edit changes its own line rather than moving it to the top."""
    snapshot = GeminiMemoryImporter().snapshot(EXAMPLE)

    assert snapshot.listed == {SAVED_INFO}
    assert snapshot.files == {
        SAVED_INFO: ({}, "# Saved info\n\n- Writes in British English.\n- Prefers tea to coffee.\n"),
    }


def test_snapshot_multiline_item_stays_one_bullet(tmp_path):
    archive = _archive(tmp_path, [_item("First line.\nSecond line.", 1, 1)])

    [(_, body)] = GeminiMemoryImporter().snapshot(archive).files.values()

    assert body == "# Saved info\n\n- First line.\n  Second line.\n"


def test_snapshot_null_body_raises(tmp_path):
    with pytest.raises(RuntimeError, match="ZKcapf"):
        GeminiMemoryImporter().snapshot(_archive(tmp_path, None))


def test_autodetect_example_archive_finds_the_gemini_memory_importer():
    assert isinstance(autodetect_importer(EXAMPLE), GeminiMemoryImporter)


def test_landing_tree_gemini_memory_lands_in_memory_gemini():
    assert landing_tree("gemini-memory") == Path("memory/gemini")


# ---------------------------------------------------------------------------
# Fetcher
# ---------------------------------------------------------------------------


def test_fetch_records_one_saved_info_call(tmp_path):
    gemini = FakeGemini()
    archive = gemini.fetcher().fetch(tmp_path, since=None)

    assert read_header(archive).source == "gemini-memory"
    [entry] = read_entries(archive)
    assert (entry["rpc"], entry["payload"], entry["response"]) == ("ZKcapf", [], gemini.response)
    [request] = gemini.requests
    assert request.url.params["source-path"] == "/saved-info"


def test_fetch_with_cursor_after_every_update_still_archives(tmp_path):
    """The listing is the only evidence of a deletion, so it is captured whatever the cursor says."""
    archive = FakeGemini().fetcher().fetch(tmp_path, since=datetime(2030, 1, 1, tzinfo=UTC))

    assert archive is not None


def test_fetch_without_session_cookie_returns_none(tmp_path):
    assert FakeGemini().fetcher(cookies={}).fetch(tmp_path, since=None) is None


def test_fetch_null_body_raises(tmp_path):
    gemini = FakeGemini()
    gemini.response = _response(None)

    with pytest.raises(RuntimeError, match="ZKcapf"):
        gemini.fetcher().fetch(tmp_path, since=None)


# ---------------------------------------------------------------------------
# Through `fetch` into the mirror
# ---------------------------------------------------------------------------


def test_fetch_command_mirrors_into_memory_gemini(test_repo):
    fetch(test_repo, fetchers=[FakeGemini().fetcher()], auto_index=False)

    metadata, body = load_frontmatter((test_repo.root / "memory/gemini/saved-info.md").read_text())
    assert body == "# Saved info\n\n- Writes in British English.\n- Prefers tea to coffee.\n"
    assert metadata["source"] == "gemini-memory"


def test_fetch_command_unchanged_upstream_leaves_no_trace(test_repo):
    """Every capture carries every item; one that matches the tree stores no blob and makes no commit."""
    fetch(test_repo, fetchers=[FakeGemini().fetcher()], auto_index=False)
    head, blobs = git(test_repo.root, "rev-parse", "HEAD"), _blobs(test_repo)

    fetch(test_repo, fetchers=[FakeGemini().fetcher()], auto_index=False)

    assert git(test_repo.root, "rev-parse", "HEAD") == head
    assert _blobs(test_repo) == blobs


def test_fetch_command_upstream_deletion_rewrites_the_file(test_repo):
    fetch(test_repo, fetchers=[FakeGemini([_item("Kept.", 1, 1), _item("Dropped.", 2, 2)]).fetcher()], auto_index=False)

    fetch(test_repo, fetchers=[FakeGemini([_item("Kept.", 1, 1)]).fetcher()], auto_index=False)

    _, body = load_frontmatter((test_repo.root / "memory/gemini/saved-info.md").read_text())
    assert body == "# Saved info\n\n- Kept.\n"
