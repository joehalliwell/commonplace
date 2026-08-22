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
