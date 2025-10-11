import subprocess
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from commonplace._utils import edit_in_editor, slugify, truncate


def test_truncate_short_text():
    result = truncate("Hello", max_length=200)
    assert result == "Hello"


def test_truncate_long_text():
    long_text = "a" * 250
    result = truncate(long_text, max_length=200)
    assert len(result) > 200  # Due to the "more" suffix
    assert result.endswith(" (+50 more)")
    assert result.startswith("a" * 200)


def test_truncate_exact_length():
    text = "a" * 200
    result = truncate(text, max_length=200)
    assert result == text


def test_truncate_custom_max_length():
    result = truncate("Hello world", max_length=5)
    assert result == "Hello (+6 more)"


def test_slugify_basic():
    result = slugify("Hello World")
    assert result == "hello-world"


def test_slugify_with_special_chars():
    result = slugify("Hello, World! & More")
    assert result == "hello-world--more"


def test_slugify_with_numbers():
    result = slugify("Test 123 ABC")
    assert result == "test-123-abc"


def test_slugify_empty_string():
    result = slugify("")
    assert result == ""


def test_slugify_only_special_chars():
    result = slugify("!@#$%^&*()")
    assert result == ""


def test_slugify_consecutive_spaces():
    result = slugify("Hello    World")
    assert result == "hello----world"


def test_slugify_leading_trailing_spaces():
    result = slugify("  Hello World  ")
    assert result == "--hello-world--"


def test_edit_in_editor_with_changes(tmp_path):
    """Test editing content that gets changed."""
    original = "Original content"
    edited = "Edited content"

    with (
        patch("commonplace._utils.subprocess.run") as mock_run,
        patch("commonplace._utils.tempfile.NamedTemporaryFile") as mock_tempfile,
    ):
        # Setup temp file mock
        temp_file = tmp_path / "temp.txt"
        mock_temp = Mock()
        mock_temp.name = str(temp_file)
        mock_tempfile.return_value = mock_temp

        # Simulate editor changing the content
        def write_edited_content(*args, **kwargs):
            temp_file.write_text(edited)

        mock_run.side_effect = write_edited_content

        # Patch Path methods
        with (
            patch.object(Path, "write_text") as _,
            patch.object(Path, "read_text") as mock_read,
            patch.object(Path, "unlink") as mock_unlink,
        ):
            mock_read.side_effect = [edited]  # Return edited content

            result = edit_in_editor(original, "vim")

            assert result == edited
            mock_run.assert_called_once()
            assert mock_run.call_args[0][0] == ["vim", str(temp_file)]
            mock_unlink.assert_called_once()


def test_edit_in_editor_no_changes(tmp_path):
    """Test editing content that doesn't change."""
    content = "Unchanged content"

    with (
        patch("commonplace._utils.subprocess.run") as mock_run,
        patch("commonplace._utils.tempfile.NamedTemporaryFile") as mock_tempfile,
    ):
        # Setup temp file mock
        temp_file = tmp_path / "temp.txt"
        mock_temp = Mock()
        mock_temp.name = str(temp_file)
        mock_tempfile.return_value = mock_temp

        with (
            patch.object(Path, "write_text"),
            patch.object(Path, "read_text") as mock_read,
            patch.object(Path, "unlink") as mock_unlink,
        ):
            mock_read.return_value = content  # Return same content

            result = edit_in_editor(content, "vim")

            assert result is None
            mock_run.assert_called_once()
            mock_unlink.assert_called_once()


def test_edit_in_editor_editor_fails(tmp_path):
    """Test handling editor exit with error code."""
    content = "Some content"

    with (
        patch("commonplace._utils.subprocess.run") as mock_run,
        patch("commonplace._utils.tempfile.NamedTemporaryFile") as mock_tempfile,
    ):
        # Setup temp file mock
        temp_file = tmp_path / "temp.txt"
        mock_temp = Mock()
        mock_temp.name = str(temp_file)
        mock_tempfile.return_value = mock_temp

        mock_run.side_effect = subprocess.CalledProcessError(1, "vim")

        with patch.object(Path, "write_text"), patch.object(Path, "unlink"):
            with pytest.raises(subprocess.CalledProcessError):
                edit_in_editor(content, "vim")


def test_edit_in_editor_editor_not_found(tmp_path):
    """Test handling editor not found."""
    content = "Some content"

    with (
        patch("commonplace._utils.subprocess.run") as mock_run,
        patch("commonplace._utils.tempfile.NamedTemporaryFile") as mock_tempfile,
    ):
        # Setup temp file mock
        temp_file = tmp_path / "temp.txt"
        mock_temp = Mock()
        mock_temp.name = str(temp_file)
        mock_tempfile.return_value = mock_temp

        mock_run.side_effect = FileNotFoundError("vim not found")

        with patch.object(Path, "write_text"), patch.object(Path, "unlink"):
            with pytest.raises(FileNotFoundError):
                edit_in_editor(content, "vim")
