"""Tests for marginalia: what's been said about a note since, kept in a shadow tree beside it."""

import shutil
from pathlib import Path

import pytest

from commonplace._marginalia import MARGINALIA_VERSION, Sidecar, read_sidecar, sidecar_path, write_sidecar
from commonplace._utils import load_frontmatter

EXAMPLES = Path(__file__).parent / "resources" / "marginalia"
NODE = Path("notes/ideas.md")


@pytest.fixture(params=range(1, MARGINALIA_VERSION + 1), ids=lambda v: f"marginalia-v{v}")
def any_marginalia_version(request, tmp_path) -> Path:
    """A repo root holding one example sidecar per format version, all for `NODE` with the same content."""
    source = EXAMPLES / f"v{request.param}.md"
    if not source.exists():
        pytest.fail(f"marginalia v{request.param} has no example at {source} — add one with the version bump")
    target = tmp_path / sidecar_path(NODE)
    target.parent.mkdir(parents=True)
    shutil.copyfile(source, target)
    return tmp_path


def test_every_marginalia_version_reads_to_the_same_sidecar(any_marginalia_version):
    sidecar = read_sidecar(any_marginalia_version, NODE)

    assert sidecar.tags == ["hidden", "tea"]
    assert "[[/notes/todo]]" in sidecar.body


def test_a_note_without_a_sidecar_reads_as_untagged(tmp_path):
    assert read_sidecar(tmp_path, NODE) == Sidecar(node=NODE)


def test_a_sidecar_lives_at_the_notes_path_in_the_shadow_tree():
    assert sidecar_path(Path("chats/claude/2026/06/tea.md")) == Path(
        ".commonplace/marginalia/chats/claude/2026/06/tea.md"
    )


def test_tags_round_trip_through_the_shadow_tree(test_repo):
    write_sidecar(test_repo, Sidecar(node=NODE).tagged("hidden", "tea"))

    assert read_sidecar(test_repo.root, NODE).tags == ["hidden", "tea"]
    metadata, _ = load_frontmatter((test_repo.root / sidecar_path(NODE)).read_text())
    assert metadata["marginalia"] == MARGINALIA_VERSION


def test_tagging_again_with_a_tag_it_has_adds_nothing():
    assert Sidecar(node=NODE).tagged("tea").tagged("tea", "hidden").tags == ["tea", "hidden"]


def test_untagging_leaves_the_body_alone():
    """The body is the log, appended to and never rewritten by tag changes."""
    sidecar = Sidecar(node=NODE, tags=["tea", "hidden"], body="- 2026-11-01 filed as [[/notes/todo]]\n")

    assert sidecar.untagged("hidden") == Sidecar(node=NODE, tags=["tea"], body=sidecar.body)


def test_a_sidecar_newer_than_this_release_is_refused(tmp_path):
    """Its fields are unknown here, so rewriting it could lose them."""
    target = tmp_path / sidecar_path(NODE)
    target.parent.mkdir(parents=True)
    target.write_text(f"---\nmarginalia: {MARGINALIA_VERSION + 1}\ntags:\n- tea\n---\n")

    with pytest.raises(ValueError, match="newer"):
        read_sidecar(tmp_path, NODE)
