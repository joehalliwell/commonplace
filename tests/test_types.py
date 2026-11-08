from pathlib import Path

import pytest

from commonplace._types import Note


@pytest.mark.parametrize("path", ["../escape.md", "memory/../../escape.md", "/abs.md"])
def test_note_whose_path_could_leave_the_repo_is_refused(path):
    with pytest.raises(ValueError):
        Note(Path(path), "")


def test_note_path_is_normalised_relative_to_the_root():
    assert Note(Path("memory/claude/a/../b.md"), "").path == Path("memory/claude/b.md")


def test_note_compose_leads_metadata_with_type_and_title_and_leaves_body_alone():
    note = Note.compose(Path("memory/x/a.md"), "Memory", "Tea", "Prefers tea.\n", {"updated_at": "t"})

    assert list(note.metadata.items()) == [("type", "Memory"), ("title", "Tea"), ("updated_at", "t")]
    assert note.body == "Prefers tea.\n"
