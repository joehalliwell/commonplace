import subprocess
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import yaml

from commonplace._utils import batched, edit_in_editor, merge_frontmatter, parse_frontmatter, slugify, truncate


def test_batched_basic():
    """Test batching a simple list."""
    items = [1, 2, 3, 4, 5, 6, 7]
    batches = list(batched(items, 3))

    assert len(batches) == 3
    assert batches[0] == [1, 2, 3]
    assert batches[1] == [4, 5, 6]
    assert batches[2] == [7]


def test_batched_exact_multiple():
    """Test batching when items divide evenly."""
    items = [1, 2, 3, 4, 5, 6]
    batches = list(batched(items, 2))

    assert len(batches) == 3
    assert batches[0] == [1, 2]
    assert batches[1] == [3, 4]
    assert batches[2] == [5, 6]


def test_batched_single_batch():
    """Test when all items fit in one batch."""
    items = [1, 2, 3]
    batches = list(batched(items, 10))

    assert len(batches) == 1
    assert batches[0] == [1, 2, 3]


def test_batched_empty():
    """Test batching an empty iterable."""
    items = []
    batches = list(batched(items, 5))

    assert len(batches) == 0


def test_batched_generator():
    """Test batching a generator."""

    def gen():
        yield from range(10)

    batches = list(batched(gen(), 3))

    assert len(batches) == 4
    assert batches[0] == [0, 1, 2]
    assert batches[3] == [9]


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


def test_parse_frontmatter_with_metadata():
    content = """---
uuid: abc123
model: claude-3
---

# Test Content

Body here."""
    metadata, body = parse_frontmatter(content)

    assert metadata == {"uuid": "abc123", "model": "claude-3"}
    assert body.strip().startswith("# Test Content")


def test_parse_frontmatter_no_metadata():
    content = "# Test Content\n\nNo frontmatter here."
    metadata, body = parse_frontmatter(content)

    assert metadata == {}
    assert body == content


def test_parse_frontmatter_invalid_yaml():
    content = """---
invalid: [unclosed
---

Body"""
    with pytest.raises(yaml.YAMLError):
        parse_frontmatter(content)


def test_parse_frontmatter_no_closing_delimiter():
    content = """---
uuid: abc123

# This looks like content but no closing ---"""
    metadata, body = parse_frontmatter(content)

    # Should treat as no frontmatter
    assert metadata == {}
    assert body == content


def test_merge_frontmatter_preserves_user_fields():
    existing = """---
uuid: abc123
model: claude-3
tags: [python, debugging]
rating: 5
---

Content"""
    new_metadata = {"uuid": "abc123", "model": "claude-3-5"}

    merged = merge_frontmatter(existing, new_metadata)

    assert merged["uuid"] == "abc123"
    assert merged["model"] == "claude-3-5"  # Updated by importer
    assert merged["tags"] == ["python", "debugging"]  # Preserved
    assert merged["rating"] == 5  # Preserved


def test_merge_frontmatter_no_existing():
    existing = "# Content\n\nNo frontmatter"
    new_metadata = {"uuid": "new123", "model": "claude-3"}

    merged = merge_frontmatter(existing, new_metadata)

    assert merged == new_metadata
