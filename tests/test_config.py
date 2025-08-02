import os
from pathlib import Path
from unittest import mock

import pytest

from commonplace import get_config


def test_config_root_env_var(tmpdir):
    """Test that get_config() uses COMMONPLACE_ROOT environment variable."""
    get_config.cache_clear()
    with mock.patch.dict(os.environ, {"COMMONPLACE_ROOT": str(tmpdir)}):
        config = get_config()
        assert config.root == Path(tmpdir)


@pytest.mark.parametrize("bad_dir", ["", "/nonexistent/directory"])
def test_config_fails_with_empty_root_env_var(bad_dir):
    """Test that get_config() fails gracefully when COMMONPLACE_ROOT is empty."""
    get_config.cache_clear()
    with mock.patch.dict(os.environ, {"COMMONPLACE_ROOT": bad_dir}):
        with pytest.raises(SystemExit) as exc_info:
            get_config()
        assert exc_info.value.code == 1
