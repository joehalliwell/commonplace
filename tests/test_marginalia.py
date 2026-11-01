"""Tests for marginalia: what's been said about a note since, kept in a shadow tree beside it."""

import shutil
from pathlib import Path

import pytest

from commonplace._links import UnresolvedNote
from commonplace._marginalia import (
    MARGINALIA_VERSION,
    Sidecar,
    read_sidecar,
    sidecar_path,
    tag,
    untag,
    write_sidecar,
)
from commonplace._utils import load_frontmatter
from tests.porcelain import git

EXAMPLES = Path(__file__).parent / "resources" / "marginalia"
NODE = Path("notes/ideas.md")


@pytest.fixture
def notes(test_repo, make_note):
    """A repo with a few committed notes."""
    for path in ("notes/ideas.md", "chats/claude-tasks/2026/10/log.md", "chats/claude-tasks/2026/11/log.md"):
        test_repo.save(make_note(path=path, content=f"# {path}\n\nSome text.\n"))
    test_repo.commit("Add notes", auto_index=False)
    return test_repo


@pytest.fixture
def as_joe(monkeypatch):
    """Joe's identity, as git would find it in his config."""
    for role in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{role}_NAME", "Joe")
        monkeypatch.setenv(f"GIT_{role}_EMAIL", "joe@example.com")


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


def test_tag_records_the_tags_and_the_notes_ref(notes, as_joe):
    tag(notes, "ideas", ["hidden", "tea"])

    sidecar = read_sidecar(notes.root, NODE)
    assert sidecar.tags == ["hidden", "tea"]
    assert sidecar.ref == notes.make_repo_path(NODE).ref


def test_tag_commits_as_the_person_not_the_bot(notes, as_joe):
    """Tools tell a person's tags from their own by the commit's author, so they never remove them."""
    tag(notes, "ideas", ["hidden"])

    assert git(notes.root, "log", "-1", "--format=%an") == "Joe\n"


def test_tag_a_glob_tags_every_match(notes, as_joe):
    tag(notes, "/chats/claude-tasks/**", ["scheduled"])

    for month in ("10", "11"):
        assert read_sidecar(notes.root, Path(f"chats/claude-tasks/2026/{month}/log.md")).tags == ["scheduled"]


def test_untag_removes_only_the_tags_named(notes, as_joe):
    tag(notes, "ideas", ["hidden", "tea"])

    untag(notes, "ideas", ["hidden"])

    assert read_sidecar(notes.root, NODE).tags == ["tea"]


def test_tag_a_span_is_refused(notes, as_joe):
    """Tags describe whole notes; only edges reach inside one."""
    with pytest.raises(UnresolvedNote, match="whole notes"):
        tag(notes, "ideas#Tea house", ["hidden"])


def test_tag_cli_shows_a_notes_tags_when_given_none(notes, as_joe, test_app, capsys):
    assert test_app(["tag", "ideas", "hidden", "tea"]) == 0
    capsys.readouterr()

    assert test_app(["tag", "ideas"]) == 0

    assert capsys.readouterr().out.split() == ["hidden", "tea"]


def test_a_sidecar_newer_than_this_release_is_refused(tmp_path):
    """Its fields are unknown here, so rewriting it could lose them."""
    target = tmp_path / sidecar_path(NODE)
    target.parent.mkdir(parents=True)
    target.write_text(f"---\nmarginalia: {MARGINALIA_VERSION + 1}\ntags:\n- tea\n---\n")

    with pytest.raises(ValueError, match="newer"):
        read_sidecar(tmp_path, NODE)
