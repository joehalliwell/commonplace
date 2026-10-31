from pathlib import Path

from commonplace._types import Note, RepoPath


def test_repo_path_without_ref_is_uncommitted_and_prints_bare():
    repo_path = RepoPath(Path("notes/idea.md"))

    assert repo_path.ref is None
    assert str(repo_path) == "notes/idea.md"


def test_note_compose_leads_metadata_with_type_and_title_and_heads_body_with_title():
    note = Note.compose(RepoPath(Path("memory/x/a.md")), "Memory", "Tea", "\nPrefers tea.\n", {"updated_at": "t"})

    assert list(note.metadata.items()) == [("type", "Memory"), ("title", "Tea"), ("updated_at", "t")]
    assert note.body == "# Tea\n\nPrefers tea.\n"
    assert note.repo_path.ref is None
