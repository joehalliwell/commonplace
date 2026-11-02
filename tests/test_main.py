import tomllib

import pytest
from cyclopts.exceptions import CycloptsError

from commonplace.__main__ import app
from commonplace._config import Config
from commonplace._repo import Commonplace


def test_init(tmp_path):
    root = tmp_path / "new_repo"
    assert app.meta(["init", str(root)], result_action="return_int_as_exit_code_else_zero") == 0
    Commonplace.open(root)


def test_search_empty_index_exits_cleanly(test_app):
    assert test_app(["search", "help"]) == 0


def test_stats_empty_repo_prints_a_table(test_app, capsys):
    assert test_app(["stats"]) == 0

    assert capsys.readouterr().out.strip()


@pytest.mark.parametrize("argv", [["import", "export.zip"], ["fetch"], ["journal"]], ids=lambda argv: argv[0])
def test_no_index_flag_is_understood_by_every_note_creating_command(argv):
    _, bound, _ = app.parse_args([*argv, "--no-index"])

    assert bound.arguments["index"] is False


# ---------------------------------------------------------------------------
# The command surface, settled before 1.0: what each name binds to, and the old names gone.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("argv", "name", "value"),
    [
        (["fetch", "--full"], "full", True),
        (["stats", "--all"], "all_time", True),
        (["journal", "--date", "2026-11-01"], "date", "2026-11-01"),
        (["link", "--note", "a", "--target", "b"], "note", "a"),
        (["unlink", "--note", "a", "--target", "b"], "note", "a"),
        (["search", "tea", "--hidden"], "hidden", True),
        (["search", "tea", "--deleted"], "deleted", True),
        (["ls", "--hidden"], "hidden", True),
        (["show", "ideas", "--hidden"], "hidden", True),
    ],
    ids=lambda value: value[0] if isinstance(value, list) else None,
)
def test_cli_names_bind_as_documented(argv, name, value):
    _, bound, _ = app.parse_args(argv)

    assert bound.arguments[name] == value


@pytest.mark.parametrize(
    ("argv", "name"),
    [
        (["search", "tea", "--no-hidden"], "hidden"),
        (["search", "tea", "--no-deleted"], "deleted"),
        (["show", "ideas", "--no-json"], "as_json"),
        (["doctor", "--no-check"], "check"),
        (["fetch", "--no-full"], "full"),
        (["stats", "--no-all"], "all_time"),
    ],
    ids=lambda value: " ".join(value) if isinstance(value, list) else None,
)
def test_every_boolean_flag_has_a_no_form(argv, name):
    """One convention: a flag is named so that its --no- form reads naturally, and has one."""
    _, bound, _ = app.parse_args(argv)

    assert bound.arguments[name] is False


def test_no_verbose_overrides_the_environment():
    _, bound, _ = app.meta.parse_args(["--no-verbose", "config"])

    assert bound.arguments["verbose"] is False


def test_stats_takes_folders_like_ls(test_app, capsys):
    """--source meant a source on fetch and a path prefix on stats; stats now takes folders, as ls does."""
    _, bound, _ = app.parse_args(["stats", "chats/claude", "journal"])

    assert bound.arguments["folders"] == ("chats/claude", "journal")


@pytest.mark.parametrize(
    "argv",
    [
        ["fetch", "--all"],
        ["stats", "--source", "journal"],
        ["journal", "--date-str", "2026-11-01"],
        ["link", "--source", "a", "--target", "b"],
        ["search", "tea", "--include-hidden"],
        ["search", "tea", "--include-deleted"],
        ["ls", "--include-hidden"],
    ],
    ids=lambda argv: " ".join(argv),
)
def test_names_retired_before_1_0_are_refused(argv):
    with pytest.raises(CycloptsError):
        app.parse_args(argv, exit_on_error=False, print_error=False)


def test_tag_without_tags_is_refused_now_that_show_shows_them(test_app, test_repo, make_note):
    test_repo.save(make_note(path="notes/ideas.md", content="# Ideas\n"))
    test_repo.commit("Add", auto_index=False)

    with pytest.raises(SystemExit):
        test_app(["tag", "ideas"])


def test_config_prints_merged_settings_as_toml(test_app, test_repo, capsys, monkeypatch):
    monkeypatch.delenv("COMMONPLACE_USER", raising=False)
    (test_repo.root / ".commonplace" / "config.toml").write_text('user = "Repo"\n')

    assert test_app(["config"]) == 0

    settings = tomllib.loads(capsys.readouterr().out)
    assert settings["user"] == "Repo"
    assert settings.keys() == Config.model_fields.keys()


def test_config_key_prints_bare_value(test_app, test_repo, capsys, monkeypatch):
    monkeypatch.setenv("COMMONPLACE_USER", "Env")
    (test_repo.root / ".commonplace" / "config.toml").write_text('user = "Repo"\n')

    assert test_app(["config", "user"]) == 0

    assert capsys.readouterr().out == "Env\n"


def test_config_key_prints_non_strings_as_toml(test_app, capsys, monkeypatch):
    monkeypatch.setenv("COMMONPLACE_AUTO_INDEX", "false")

    assert test_app(["config", "auto_index"]) == 0

    assert capsys.readouterr().out == "false\n"


def test_config_unknown_key_fails_naming_valid_keys(test_app, caplog):
    with pytest.raises(SystemExit):
        test_app(["config", "usr"])

    assert "user" in caplog.text
