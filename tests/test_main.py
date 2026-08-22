from commonplace._repo import Commonplace


def test_init(tmp_path):
    from commonplace.__main__ import app

    root = tmp_path / "new_repo"
    assert app.meta(["init", str(root)], result_action="return_int_as_exit_code_else_zero") == 0
    Commonplace.open(root)


def test_search(test_app):
    test_app(["search", "help"])


def test_stats(test_app):
    test_app(["stats"])


def test_links_reports_a_broken_link(test_app, test_repo, capsys):
    (test_repo.root / "notes").mkdir()
    (test_repo.root / "notes" / "note.md").write_text("See [the other one](gone.md).\n")

    test_app(["links"])

    assert "gone.md" in capsys.readouterr().out


def test_links_all_lists_working_links_too(test_app, test_repo, capsys):
    (test_repo.root / "notes").mkdir()
    (test_repo.root / "notes" / "target.md").write_text("# Target\n")
    (test_repo.root / "notes" / "note.md").write_text("See [it](target.md).\n")

    test_app(["links", "--all"])

    assert "target.md" in capsys.readouterr().out
