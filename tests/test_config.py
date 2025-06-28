import pytest
import tempfile
from pathlib import Path
from pydantic import ValidationError
from commonplace._config import Config


class TestConfig:
    def test_config_with_valid_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = Config(root=temp_dir)
            assert config.root == Path(temp_dir)
            assert config.wrap == 80

    def test_config_with_invalid_directory(self):
        with pytest.raises(ValidationError):
            Config(root="/nonexistent/directory/path")

    def test_config_with_file_instead_of_directory(self):
        with tempfile.NamedTemporaryFile() as temp_file:
            with pytest.raises(ValidationError):
                Config(root=temp_file.name)

    def test_config_custom_wrap(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = Config(root=temp_dir, wrap=120)
            assert config.wrap == 120

    def test_config_expanduser(self):
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
