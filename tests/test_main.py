import tomllib

import pytest

from commonplace._config import Config
from commonplace._repo import Commonplace


def test_init(tmp_path):
    from commonplace.__main__ import app

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
    from commonplace.__main__ import app

    _, bound, _ = app.parse_args([*argv, "--no-index"])

    assert bound.arguments["index"] is False


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
