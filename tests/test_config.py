import pytest
from pydantic import ValidationError

from commonplace._config import Config


@pytest.fixture
def layers(tmp_path, monkeypatch):
    """A repo root and a global config file, with no COMMONPLACE_ settings leaking in from the environment."""
    for name in ("COMMONPLACE_USER", "COMMONPLACE_EDITOR", "COMMONPLACE_WRAP"):
        monkeypatch.delenv(name, raising=False)
    root = tmp_path / "repo"
    (root / ".commonplace").mkdir(parents=True)
    global_file = tmp_path / "global" / "config.toml"
    global_file.parent.mkdir()
    return root, global_file


def test_config_no_files_uses_defaults(layers):
    root, global_file = layers

    assert Config.load(root, global_file=global_file).wrap == 80


def test_config_global_file_overrides_default(layers):
    root, global_file = layers
    global_file.write_text("wrap = 100\n")

    assert Config.load(root, global_file=global_file).wrap == 100


def test_config_repo_file_overrides_global(layers):
    root, global_file = layers
    global_file.write_text('user = "Global"\neditor = "nano"\n')
    (root / ".commonplace" / "config.toml").write_text('user = "Repo"\n')

    config = Config.load(root, global_file=global_file)

    assert (config.user, config.editor) == ("Repo", "nano")


def test_config_env_overrides_repo_file(layers, monkeypatch):
    root, global_file = layers
    (root / ".commonplace" / "config.toml").write_text("wrap = 100\n")
    monkeypatch.setenv("COMMONPLACE_WRAP", "120")

    assert Config.load(root, global_file=global_file).wrap == 120


def test_config_unknown_key_rejected(layers):
    root, global_file = layers
    (root / ".commonplace" / "config.toml").write_text('usr = "Typo"\n')

    with pytest.raises(ValidationError):
        Config.load(root, global_file=global_file)
