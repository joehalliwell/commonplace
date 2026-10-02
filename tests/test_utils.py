import subprocess
from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from commonplace._utils import (
    batched,
    dump_frontmatter,
    edit_in_editor,
    load_frontmatter,
    slugify,
    truncate,
)


@pytest.mark.parametrize(
    ("items", "size", "expected"),
    [
        pytest.param([1, 2, 3, 4, 5, 6, 7], 3, [[1, 2, 3], [4, 5, 6], [7]], id="ragged-last-batch"),
        pytest.param([1, 2, 3, 4, 5, 6], 2, [[1, 2], [3, 4], [5, 6]], id="exact-multiple"),
        pytest.param([1, 2, 3], 10, [[1, 2, 3]], id="single-batch"),
        pytest.param([], 5, [], id="empty"),
        pytest.param((n for n in range(7)), 3, [[0, 1, 2], [3, 4, 5], [6]], id="generator"),
    ],
)
def test_batched_splits_into_runs_of_size(items, size, expected):
    assert list(batched(items, size)) == expected


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

        with (
            patch.object(Path, "write_text"),
            patch.object(Path, "unlink"),
            pytest.raises(subprocess.CalledProcessError),
        ):
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

        with patch.object(Path, "write_text"), patch.object(Path, "unlink"), pytest.raises(FileNotFoundError):
            edit_in_editor(content, "vim")


def test_load_frontmatter_with_metadata():
    content = """---
uuid: abc123
model: claude-3
---

# Test Content

Body here."""
    metadata, body = load_frontmatter(content)

    assert metadata == {"uuid": "abc123", "model": "claude-3"}
    assert body.strip().startswith("# Test Content")


def test_load_frontmatter_no_metadata():
    content = "# Test Content\n\nNo frontmatter here."
    metadata, body = load_frontmatter(content)

    assert metadata == {}
    assert body == content


@pytest.mark.parametrize(
    "content",
    [
        "---\ninvalid: [unclosed\n---\n\nBody",
        "---\n\nA rule, some prose, and another rule.\n\n---\n\nBody",
        "---\n- a\n- list\n---\n\nBody",
    ],
)
def test_load_frontmatter_not_a_mapping_is_all_body(content):
    """Any markdown file may open with a rule (#95)."""
    assert load_frontmatter(content) == ({}, content)


def test_load_frontmatter_blank_line_after_block_is_not_body():
    assert load_frontmatter("---\na: 1\n---\n\n# Title\n") == load_frontmatter("---\na: 1\n---\n# Title\n")


def test_load_frontmatter_no_closing_delimiter():
    content = """---
uuid: abc123

# This looks like content but no closing ---"""
    metadata, body = load_frontmatter(content)

    # Should treat as no frontmatter
    assert metadata == {}
    assert body == content


@pytest.mark.parametrize(
    "value",
    [
        "Research: a plan",
        "issue #91",
        "- not a list",
        "[not, a, list]",
        "'quoted' and \"quoted\"",
        "2024-01-01",
        "true",
        "café ☕ 日本語",
        "first line\n---\nthird line",
        "long " * 40,
        "",
        date(2024, 1, 1),
        datetime(2024, 1, 1, 12, 0, tzinfo=UTC),
        ["a: b", "c #d"],
        [{"id": "x", "resource": "/chats/a.md"}],
        {"nested": {"deeper": ["value: 1"]}},
        None,
        5,
    ],
)
def test_dump_frontmatter_awkward_value_loads_back_unchanged(value):
    metadata, body = {"plain": "value", "awkward": value}, "\n# Title\n\nBody\n\n---\n\nAfter a rule\n"

    assert load_frontmatter(dump_frontmatter(metadata, body)) == (metadata, body)


def test_dump_frontmatter_long_path_stays_on_one_line():
    """A folded path cannot be found by searching for it."""
    path = f".commonplace/blobs/{'0' * 64}/My Activity.html"

    assert path in dump_frontmatter({"source_exports": [path]}, "")


def test_dump_frontmatter_no_metadata_is_the_body_alone():
    assert dump_frontmatter({}, "Body\n") == "Body\n"
