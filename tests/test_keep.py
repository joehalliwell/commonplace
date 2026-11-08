"""Tests for mirroring Google Keep into `notes/keep/`: fetcher, importer, and the path between."""

import copy
import json
from pathlib import Path

import httpx
import pytest

from commonplace._fetch._commands import fetch
from commonplace._fetch._helpers import FetchBlocked, NoSession
from commonplace._fetch._keep import CHECKPOINT_EVERY, KeepFetcher
from commonplace._import._commands import autodetect_importer, import_
from commonplace._import._keep import KeepImporter
from commonplace._marginalia import Marginalia, write_marginalia
from commonplace._sources import importers
from commonplace._types import MirrorSource
from commonplace._utils import load_frontmatter
from commonplace._wire import archive_names, read_entries, write_archive
from tests.fetching import fetching, owned

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
            target = json.loads(request.content).get("targetVersion")
            if target in self.pages:
                return httpx.Response(200, json=self.pages[target])
            # Changes since a version it doesn't know: everything, which is always a correct answer.
            nodes = [node for page in self.pages.values() for node in page["nodes"]]
            return httpx.Response(200, json={"toVersion": f"{target}+", "truncated": False, "nodes": nodes})
        return httpx.Response(404)

    def fetcher(self, cookies=COOKIES) -> KeepFetcher:
        return owned(KeepFetcher, cookies=cookies, transport=httpx.MockTransport(self))


def _notes() -> dict[Path, tuple[dict, str]]:
    return {note.repo_path.path: (note.metadata, note.body) for note in owned(KeepImporter).snapshot(EXAMPLE).notes}


# ---------------------------------------------------------------------------
# Importer
# ---------------------------------------------------------------------------


def test_example_archive_is_claimed_by_the_keep_importer():
    assert isinstance(autodetect_importer(EXAMPLE, importers(MirrorSource)), KeepImporter)


def test_snapshot_lands_each_note_by_its_creation_month_and_title():
    metadata, body = _notes()[TEA]

    assert body == "# Tea house\n\nA tea house by the river.\n"
    assert metadata["title"] == "Tea house"
    assert metadata["id"] == "note-tea"
    assert metadata["created"] == "2026-05-03T09:00:00.000Z"
    assert (metadata["tags"], metadata["pinned"], metadata["archived"]) == (["words"], True, False)


def test_snapshot_writes_keeps_labels_as_tags_and_no_field_when_there_are_none():
    """OKF's word, as marginalia use: a Keep label is what the note is, so frontmatter, but one vocabulary."""
    tagged, _ = _notes()[TEA]
    untagged, _ = _notes()[WORD]

    assert "labels" not in tagged and tagged["tags"] == ["words"]
    assert "tags" not in untagged


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


def test_snapshot_leaves_trashed_notes_out():
    assert "note-bin" not in {metadata["id"] for metadata, _ in _notes().values()}


def test_snapshot_says_nothing_of_who_last_edited():
    """No authorship metadata: the path says whose notes these are."""
    assert "someone@example.com" not in repr(_notes())


def test_snapshot_lists_everything_so_the_mirror_can_prune():
    assert owned(KeepImporter).snapshot(EXAMPLE).unread == frozenset()


# ---------------------------------------------------------------------------
# Fetcher
# ---------------------------------------------------------------------------


def test_fetch_pages_until_keep_says_its_done(tmp_path):
    keep = FakeKeep()

    [archive] = keep.fetcher().fetch(tmp_path, since=None)

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
    fetch(test_repo, sources=fetching(FakeKeep().fetcher()), auto_index=False)

    for path in (TEA, WORD, SHOPPING):
        assert (test_repo.root / path).exists(), path


def test_fetch_lands_the_later_of_two_notes_with_the_same_day_and_title_at_the_next_free_path(test_repo):
    fetch(test_repo, sources=fetching(FakeKeep().fetcher()), auto_index=False)

    later = load_frontmatter((test_repo.root / TEA.with_stem(f"{TEA.stem}-2")).read_text())[0]
    assert (load_frontmatter((test_repo.root / TEA).read_text())[0]["id"], later["id"]) == ("note-tea", "note-tea-2")
    assert later["archived"] is True


def test_a_retitled_note_keeps_the_path_it_was_first_captured_at(test_repo):
    """Its marginalia are keyed by path, and git's rename detection fails on short notes."""
    fetch(test_repo, sources=fetching(FakeKeep().fetcher()), auto_index=False)
    retitled = copy.deepcopy(PAGES)
    retitled[None]["nodes"][0]["title"] = "Tea pavilion"

    fetch(test_repo, sources=fetching(FakeKeep(retitled).fetcher()), auto_index=False)

    _, body = load_frontmatter((test_repo.root / TEA).read_text())
    assert body.startswith("# Tea pavilion\n")
    assert not list((test_repo.root / "notes/keep").rglob("*tea-pavilion*"))


def test_a_new_note_never_takes_the_path_of_a_gone_note_that_still_has_marginalia(test_repo):
    """Marginalia outlive their note; a later note at the same path would silently inherit them."""
    fetch(test_repo, sources=fetching(FakeKeep().fetcher()), auto_index=False)
    write_marginalia(test_repo, Marginalia(note=TEA).tagged("revisit"))
    test_repo.commit("Tag", auto_index=False)
    binned = copy.deepcopy(PAGES)
    binned[None]["nodes"][0]["timestamps"]["trashed"] = "2026-11-02T08:00:00.000Z"
    fetch(test_repo, sources=fetching(FakeKeep(binned).fetcher()), auto_index=False)

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
    fetch(test_repo, sources=fetching(FakeKeep(newer).fetcher()), auto_index=False)

    assert not (test_repo.root / TEA).exists()
    third = [p for p in (test_repo.root / "notes/keep").rglob("*.md") if "A third." in p.read_text()]
    assert len(third) == 1 and third[0].relative_to(test_repo.root) != TEA


# ---------------------------------------------------------------------------
# Incremental sync: a change set since the last capture, replayed on the last full sync
# ---------------------------------------------------------------------------

#: Since the example's v2: Eggs unticked, the untitled note trashed, a new note made.
CHANGES = {
    "toVersion": "v3",
    "truncated": False,
    "nodes": [
        {**PAGES["v1"]["nodes"][1], "checked": False},
        {
            **PAGES[None]["nodes"][2],
            "timestamps": {**PAGES[None]["nodes"][2]["timestamps"], "trashed": "2026-11-03T08:00:00.000Z"},
        },
        {**PAGES[None]["nodes"][0], "id": "note-new", "title": "New", "isPinned": False, "labelIds": []},
        {**PAGES[None]["nodes"][1], "id": "item-new", "parentId": "note-new", "text": "Fresh."},
    ],
}


def _archive(tmp_path: Path, name: str, target: str | None, page: dict) -> Path:
    """An archive as the fetcher writes one: a single page from `target`."""
    entry = {"endpoint": "changes", "targetVersion": target, "response": json.dumps(page)}
    return write_archive(tmp_path / name, "keep", [entry])


def test_fetch_asks_only_for_what_changed_since_the_last_capture(tmp_path):
    keep = FakeKeep({**PAGES, "v2": CHANGES})

    [archive] = keep.fetcher().fetch(tmp_path, since=None, previous=[EXAMPLE])

    assert [json.loads(r.content).get("targetVersion") for r in keep.requests] == ["v2"]
    assert [entry["targetVersion"] for entry in read_entries(archive)] == ["v2"]


def test_fetch_checkpoints_with_a_full_sync_after_enough_change_sets(tmp_path):
    """Replaying stays bounded: every so often the chain starts again from a full sync."""
    changes = [_archive(tmp_path, f"c{i}.jsonl.gz", "v2", CHANGES) for i in range(CHECKPOINT_EVERY)]
    keep = FakeKeep()

    keep.fetcher().fetch(tmp_path, since=None, previous=[EXAMPLE, *changes])

    assert json.loads(keep.requests[0].content).get("targetVersion") is None


def test_fetch_starts_over_when_keep_asks_for_a_full_resync(tmp_path):
    keep = FakeKeep({**PAGES, "v2": {"forceFullResync": True, "toVersion": "v2", "truncated": False}})

    [archive] = keep.fetcher().fetch(tmp_path, since=None, previous=[EXAMPLE])

    assert [json.loads(r.content).get("targetVersion") for r in keep.requests] == ["v2", None, "v1"]
    assert [entry["targetVersion"] for entry in read_entries(archive)] == [None, "v1"]


def test_snapshot_replays_a_change_set_on_the_last_full_sync(tmp_path):
    changes = _archive(tmp_path, "keep-wire.jsonl.gz", "v2", CHANGES)

    snapshot = owned(KeepImporter).snapshot(changes, earlier=[EXAMPLE])

    notes = {note.repo_path.path: note for note in snapshot.notes}
    assert notes[SHOPPING].body == "# Shopping\n\n- [ ] Milk\n- [ ] Eggs\n"
    assert WORD not in notes
    assert TEA in notes  # Unchanged since the full sync, still listed
    assert any(note.metadata["id"] == "note-new" for note in snapshot.notes)
    assert snapshot.unread == frozenset()


def test_snapshot_of_a_change_set_without_a_full_sync_before_it_fails(tmp_path):
    changes = _archive(tmp_path, "keep-wire.jsonl.gz", "v2", CHANGES)

    with pytest.raises(ValueError, match="full sync"):
        owned(KeepImporter).snapshot(changes)


def test_a_second_fetch_stores_only_what_changed(test_repo):
    fetch(test_repo, sources=fetching(FakeKeep().fetcher()), auto_index=False)

    fetch(test_repo, sources=fetching(FakeKeep({**PAGES, "v2": CHANGES}).fetcher()), auto_index=False)

    archives = test_repo.stored_archives(*archive_names("keep"))
    assert len(archives) == 2
    [entry] = read_entries(test_repo.root / archives[-1])
    assert len(json.loads(entry["response"])["nodes"]) == len(CHANGES["nodes"])
    _, body = load_frontmatter((test_repo.root / SHOPPING).read_text())
    assert body == "# Shopping\n\n- [ ] Milk\n- [ ] Eggs\n"
    assert not (test_repo.root / WORD).exists()


def test_a_capture_after_the_switch_to_xz_builds_on_a_gzip_one(test_repo, tmp_path):
    """Captures stored before archives were xz still count as earlier ones, for the fetch and for the mirror."""
    gzipped = tmp_path / "keep-wire.jsonl.gz"
    gzipped.write_bytes(EXAMPLE.read_bytes())
    import_(gzipped, test_repo, user="Human", auto_index=False)

    fetch(test_repo, sources=fetching(FakeKeep({**PAGES, "v2": CHANGES}).fetcher()), auto_index=False)

    archives = test_repo.stored_archives(*archive_names("keep"))
    assert [a.name for a in archives] == ["keep-wire.jsonl.gz", "keep-wire.jsonl.xz"]
    [entry] = read_entries(test_repo.root / archives[-1])
    assert len(json.loads(entry["response"])["nodes"]) == len(CHANGES["nodes"])
    _, body = load_frontmatter((test_repo.root / SHOPPING).read_text())
    assert body == "# Shopping\n\n- [ ] Milk\n- [ ] Eggs\n"


def test_a_note_trashed_in_keep_leaves_the_mirror(test_repo):
    fetch(test_repo, sources=fetching(FakeKeep().fetcher()), auto_index=False)
    binned = copy.deepcopy(PAGES)
    binned[None]["nodes"][0]["timestamps"]["trashed"] = "2026-11-02T08:00:00.000Z"

    fetch(test_repo, sources=fetching(FakeKeep(binned).fetcher()), auto_index=False)

    assert not (test_repo.root / TEA).exists()
