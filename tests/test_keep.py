"""Tests for mirroring Google Keep into `notes/keep/`: fetcher, importer, and the path between."""

import copy
import json
from pathlib import Path

import httpx
import pytest

from commonplace._fetch._commands import fetch
from commonplace._fetch._helpers import FetchBlocked, NoSession
from commonplace._fetch._keep import KeepFetcher
from commonplace._import._commands import autodetect_importer
from commonplace._import._keep import KeepImporter
from commonplace._marginalia import Marginalia, write_marginalia
from commonplace._utils import load_frontmatter
from commonplace._wire import read_entries

EXAMPLE = Path(__file__).parent / "resources" / "wire" / "keep-v3.jsonl.gz"
PAGES = {entry["targetVersion"]: json.loads(entry["response"]) for entry in read_entries(EXAMPLE)}
COOKIES = {"SAPISID": "sapisid", "__Secure-1PSID": "psid"}

TEA = Path("notes/keep/2026/05/2026-05-03-tea-house.md")
WORD = Path("notes/keep/2026/05/2026-05-03-sesquipedalian-given-to-long-words.md")
SHOPPING = Path("notes/keep/2026/06/2026-06-01-shopping.md")


class FakeKeep:
    """Serves Keep's sync endpoint a page at a time by targetVersion, recording each request."""

    def __init__(self, pages: dict | None = None):
        self.pages = PAGES if pages is None else pages
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.host == "notes-pa.clients6.google.com" and request.url.path == "/notes/v1/changes":
            self.requests.append(request)
            return httpx.Response(200, json=self.pages[json.loads(request.content).get("targetVersion")])
        return httpx.Response(404)

    def fetcher(self, cookies=COOKIES) -> KeepFetcher:
        return KeepFetcher(cookies=cookies, transport=httpx.MockTransport(self))


def _notes() -> dict[Path, tuple[dict, str]]:
    return {note.repo_path.path: (note.metadata, note.body) for note in KeepImporter().snapshot(EXAMPLE).notes}


# ---------------------------------------------------------------------------
# Importer
# ---------------------------------------------------------------------------


def test_example_archive_is_claimed_by_the_keep_importer():
    assert isinstance(autodetect_importer(EXAMPLE), KeepImporter)


def test_snapshot_lands_each_note_by_its_creation_month_and_title():
    metadata, body = _notes()[TEA]

    assert body == "# Tea house\n\nA tea house by the river.\n"
    assert metadata["title"] == "Tea house"
    assert metadata["id"] == "note-tea"
    assert metadata["created"] == "2026-05-03T09:00:00.000Z"
    assert (metadata["labels"], metadata["pinned"], metadata["archived"]) == (["words"], True, False)


def test_snapshot_names_an_untitled_note_by_its_first_words_and_gives_it_no_heading():
    """Most Keep notes have no title; inventing a heading would only repeat the text."""
    metadata, body = _notes()[WORD]

    assert body == "Sesquipedalian: given to long words.\nAnd a second line.\n"
    assert metadata["title"] == "Sesquipedalian: given to long words."


def test_snapshot_caps_a_name_drawn_from_one_long_word():
    """A pasted URL is one 'word'; live, one ran a filename to 228 characters."""
    [link] = [path for path, (metadata, _) in _notes().items() if metadata["id"] == "note-link"]

    assert link.parent == Path("notes/keep/2026/06")
    assert len(link.stem) <= len("2026-06-02-") + 50
    assert not link.stem.endswith("-")


def test_snapshot_renders_a_list_as_checkboxes_in_keeps_order():
    _, body = _notes()[SHOPPING]

    assert body == "# Shopping\n\n- [ ] Milk\n- [x] Eggs\n"


def test_snapshot_suffixes_the_later_of_two_notes_with_the_same_day_and_title():
    later = [path for path, (metadata, _) in _notes().items() if metadata["id"] == "note-tea-2"]

    assert len(later) == 1
    assert later[0] != TEA and later[0].name.startswith("2026-05-03-tea-house-")
    assert _notes()[later[0]][0]["archived"] is True


def test_snapshot_leaves_trashed_notes_out():
    assert "note-bin" not in {metadata["id"] for metadata, _ in _notes().values()}


def test_snapshot_says_nothing_of_who_last_edited():
    """No authorship metadata: the path says whose notes these are."""
    assert "someone@example.com" not in repr(_notes())


def test_snapshot_lists_everything_so_the_mirror_can_prune():
    assert KeepImporter().snapshot(EXAMPLE).unread == frozenset()


# ---------------------------------------------------------------------------
# Fetcher
# ---------------------------------------------------------------------------


def test_fetch_pages_until_keep_says_its_done(tmp_path):
    keep = FakeKeep()

    archive = keep.fetcher().fetch(tmp_path, since=None)

    assert [json.loads(r.content).get("targetVersion") for r in keep.requests] == [None, "v1"]
    assert [entry["targetVersion"] for entry in read_entries(archive)] == [None, "v1"]


def test_fetch_signs_requests_as_keep_s_web_app_does(tmp_path):
    """SAPISIDHASH from the session cookie, and a real Origin: an X-Origin draws 'Origin doesn't match Host for XD3'."""
    keep = FakeKeep()

    keep.fetcher().fetch(tmp_path, since=None)

    headers = keep.requests[0].headers
    assert headers["Authorization"].startswith("SAPISIDHASH ")
    assert headers["Origin"] == "https://keep.google.com"
    assert "X-Origin" not in headers


def test_fetch_refuses_a_version_that_stops_advancing(tmp_path):
    stuck = {None: PAGES[None], "v1": {**PAGES[None], "toVersion": "v1"}}

    with pytest.raises(FetchBlocked):
        FakeKeep(stuck).fetcher().fetch(tmp_path, since=None)


def test_fetch_without_the_session_cookie_is_skipped(tmp_path):
    with pytest.raises(NoSession):
        FakeKeep().fetcher(cookies={"__Secure-1PSID": "psid"}).fetch(tmp_path, since=None)


# ---------------------------------------------------------------------------
# Through `fetch` into the mirror
# ---------------------------------------------------------------------------


def test_fetch_command_mirrors_keep_into_notes_keep(test_repo):
    fetch(test_repo, fetchers=[FakeKeep().fetcher()], auto_index=False)

    for path in (TEA, WORD, SHOPPING):
        assert (test_repo.root / path).exists(), path


def test_a_retitled_note_keeps_the_path_it_was_first_captured_at(test_repo):
    """Its marginalia are keyed by path, and git's rename detection fails on short notes."""
    fetch(test_repo, fetchers=[FakeKeep().fetcher()], auto_index=False)
    retitled = copy.deepcopy(PAGES)
    retitled[None]["nodes"][0]["title"] = "Tea pavilion"

    fetch(test_repo, fetchers=[FakeKeep(retitled).fetcher()], auto_index=False)

    _, body = load_frontmatter((test_repo.root / TEA).read_text())
    assert body.startswith("# Tea pavilion\n")
    assert not list((test_repo.root / "notes/keep").rglob("*tea-pavilion*"))


def test_a_new_note_never_takes_the_path_of_a_gone_note_that_still_has_marginalia(test_repo):
    """Marginalia outlive their note; a later note at the same path would silently inherit them."""
    fetch(test_repo, fetchers=[FakeKeep().fetcher()], auto_index=False)
    write_marginalia(test_repo, Marginalia(note=TEA).tagged("revisit"))
    test_repo.commit("Tag", auto_index=False)
    binned = copy.deepcopy(PAGES)
    binned[None]["nodes"][0]["timestamps"]["trashed"] = "2026-11-02T08:00:00.000Z"
    fetch(test_repo, fetchers=[FakeKeep(binned).fetcher()], auto_index=False)

    # A new note, same day and title, and earlier than the other "Tea house", so it's proposed TEA's path.
    newer = copy.deepcopy(binned)
    newer[None]["nodes"] += [
        {**PAGES[None]["nodes"][0], "id": "note-tea-3", "isPinned": False, "labelIds": []},
        {**PAGES[None]["nodes"][1], "id": "item-tea-3", "parentId": "note-tea-3", "text": "A third."},
    ]
    newer[None]["nodes"][-2]["timestamps"] = {
        **PAGES[None]["nodes"][0]["timestamps"],
        "created": "2026-05-03T12:00:00.000Z",
    }
    fetch(test_repo, fetchers=[FakeKeep(newer).fetcher()], auto_index=False)

    assert not (test_repo.root / TEA).exists()
    third = [p for p in (test_repo.root / "notes/keep").rglob("*.md") if "A third." in p.read_text()]
    assert len(third) == 1 and third[0].relative_to(test_repo.root) != TEA


def test_a_note_trashed_in_keep_leaves_the_mirror(test_repo):
    fetch(test_repo, fetchers=[FakeKeep().fetcher()], auto_index=False)
    binned = copy.deepcopy(PAGES)
    binned[None]["nodes"][0]["timestamps"]["trashed"] = "2026-11-02T08:00:00.000Z"

    fetch(test_repo, fetchers=[FakeKeep(binned).fetcher()], auto_index=False)

    assert not (test_repo.root / TEA).exists()
