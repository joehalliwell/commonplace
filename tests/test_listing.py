from pathlib import Path

import pytest

from commonplace._marginalia import Sidecar, write_sidecar


def write(root: Path, path: str, content: str = "") -> None:
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)


def listing(test_app, capsys, *args: str) -> str:
    assert test_app(["ls", *args]) == 0
    return capsys.readouterr().out


def test_ls_folded_description_lists_on_one_line(test_app, test_repo, capsys):
    write(
        test_repo.root,
        "topics/career.md",
        "---\ntitle: Career\ndescription: >-\n  Working life,\n  in three lines\n  of YAML.\n---\n\n# Career\n",
    )

    assert "- [Career](career.md) - Working life, in three lines of YAML.\n" in listing(test_app, capsys, "topics")


def test_ls_literal_block_description_collapses_newlines(test_app, test_repo, capsys):
    write(test_repo.root, "topics/a.md", "---\ndescription: |\n  First line\n  second line\n---\n")

    assert "- [a](a.md) - First line second line\n" in listing(test_app, capsys, "topics")


def test_ls_without_frontmatter_falls_back_to_the_filename(test_app, test_repo, capsys):
    write(test_repo.root, "notes/plain.md", "# Just a heading\n")

    assert "- [plain](plain.md)\n" in listing(test_app, capsys, "notes")


def test_ls_field_adds_frontmatter_values_under_the_entry(test_app, test_repo, capsys):
    write(test_repo.root, "topics/art.md", "---\ntitle: Art\nqueries:\n  - painting\n  - music\n---\n")

    out = listing(test_app, capsys, "topics", "--field", "queries", "--field", "missing")

    assert '- [Art](art.md)\n  - queries: ["painting", "music"]\n' in out
    assert "missing" not in out


def test_ls_lists_subfolders_after_files_and_skips_dot_directories(test_app, test_repo, capsys):
    write(test_repo.root, "topics/b.md", "---\ntitle: B\n---\n")
    write(test_repo.root, "topics/resonances/x-y.md", "---\ntitle: X and Y\n---\n")
    write(test_repo.root, "topics/.hidden/z.md", "---\ntitle: Z\n---\n")

    out = listing(test_app, capsys, "topics")

    assert out == "# topics\n\n- [B](b.md)\n- [resonances](resonances/)\n"


def test_ls_without_a_folder_lists_the_root(test_app, test_repo, capsys):
    write(test_repo.root, "topics/b.md", "---\ntitle: B\n---\n")

    out = listing(test_app, capsys)

    assert out.startswith("# .\n")
    assert "- [topics](topics/)\n" in out


def test_ls_unknown_folder_fails(test_app, caplog):
    with pytest.raises(SystemExit):
        test_app(["ls", "nowhere"])

    assert "nowhere" in caplog.text


def test_ls_field_tags_adds_marginalia_tags_after_the_notes_own(test_app, test_repo, capsys):
    """A note's own tags say what it is; marginalia say what's been said about it since. A listing shows both."""
    write(test_repo.root, "topics/tea.md", "---\ntitle: Tea\ntags: [drink, tea]\n---\n")
    write_sidecar(test_repo, Sidecar(node=Path("topics/tea.md")).tagged("tea", "revisit"))

    assert '  - tags: ["drink", "tea", "revisit"]\n' in listing(test_app, capsys, "topics", "--field", "tags")


def test_ls_leaves_out_hidden_notes_unless_asked(test_app, test_repo, capsys):
    """Skills gather through ls, and hidden is honoured wherever a note is offered."""
    write(test_repo.root, "notes/kept.md")
    write(test_repo.root, "notes/mood.md")
    write_sidecar(test_repo, Sidecar(node=Path("notes/mood.md")).tagged("hidden"))

    assert "mood.md" not in listing(test_app, capsys, "notes")
    assert "mood.md" in listing(test_app, capsys, "notes", "--include-hidden")
