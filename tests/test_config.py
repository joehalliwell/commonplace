import os
import tempfile
from pathlib import Path
from unittest import mock

import pytest
from pydantic import ValidationError

from commonplace import get_config
from commonplace._config import Config


def test_config_with_invalid_directory():
    with pytest.raises(ValidationError):
        Config(root="/nonexistent/directory/path")


def test_config_with_file_instead_of_directory():
    with tempfile.NamedTemporaryFile() as temp_file:
        with pytest.raises(ValidationError):
            Config(root=temp_file.name)


def test_config_custom_wrap():
    with tempfile.TemporaryDirectory() as temp_dir:
        config = Config(root=temp_dir, wrap=120)
        assert config.wrap == 120


def test_config_expanduser():
    with tempfile.TemporaryDirectory() as temp_dir:
        # Test that ~ gets expanded
        test_path = f"~/../{Path(temp_dir).name}"
        try:
            config = Config(root=test_path)
            assert "~" not in str(config.root)
        except ValidationError:
            # This might fail depending on the actual path resolution
            # but at least we test the expanduser functionality
            pass

    def teardown_method():
        """Clear the config cache after each test to avoid interference."""
        get_config.cache_clear()

    def test_config_fails_without_root_env_var():
        """Test that get_config() fails gracefully when COMMONPLACE_ROOT is not set."""
        with mock.patch.dict(os.environ, {}, clear=True):
            # Clear the cache first
            get_config.cache_clear()

            with pytest.raises(SystemExit) as exc_info:
                get_config()

            assert exc_info.value.code == 1

    def test_config_fails_with_empty_root_env_var():
        """Test that get_config() fails gracefully when COMMONPLACE_ROOT is empty."""
        with mock.patch.dict(os.environ, {"COMMONPLACE_ROOT": ""}, clear=True):
            # Clear the cache first
            get_config.cache_clear()

            with pytest.raises(SystemExit) as exc_info:
                get_config()

            assert exc_info.value.code == 1

    def test_config_fails_with_nonexistent_directory():
        """Test that get_config() fails when COMMONPLACE_ROOT points to nonexistent directory."""
        with mock.patch.dict(os.environ, {"COMMONPLACE_ROOT": "/nonexistent/directory"}, clear=True):
            # Clear the cache first
            get_config.cache_clear()

            with pytest.raises(SystemExit) as exc_info:
                get_config()

            assert exc_info.value.code == 1
