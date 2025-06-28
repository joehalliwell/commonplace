import os
import pytest
from unittest import mock
from commonplace import get_config


class TestConfigErrorHandling:
    def teardown_method(self):
        """Clear the config cache after each test to avoid interference."""
        get_config.cache_clear()

    def test_config_fails_without_root_env_var(self):
        """Test that get_config() fails gracefully when COMMONPLACE_ROOT is not set."""
        with mock.patch.dict(os.environ, {}, clear=True):
            # Clear the cache first
            get_config.cache_clear()

            with pytest.raises(SystemExit) as exc_info:
                get_config()

            assert exc_info.value.code == 1

    def test_config_fails_with_empty_root_env_var(self):
        """Test that get_config() fails gracefully when COMMONPLACE_ROOT is empty."""
        with mock.patch.dict(os.environ, {"COMMONPLACE_ROOT": ""}, clear=True):
            # Clear the cache first
            get_config.cache_clear()

            with pytest.raises(SystemExit) as exc_info:
                get_config()

            assert exc_info.value.code == 1

    def test_config_fails_with_nonexistent_directory(self):
        """Test that get_config() fails when COMMONPLACE_ROOT points to nonexistent directory."""
        with mock.patch.dict(os.environ, {"COMMONPLACE_ROOT": "/nonexistent/directory"}, clear=True):
            # Clear the cache first
            get_config.cache_clear()

            with pytest.raises(SystemExit) as exc_info:
                get_config()

            assert exc_info.value.code == 1
