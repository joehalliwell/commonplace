from datetime import datetime
from pathlib import Path

from commonplace._store import ActivityLogDirectoryStore, MarkdownSerializer
from commonplace._types import ActivityLog, Message, Role


def test_serialize_basic_log():
    """Test basic serialization of ActivityLog to markdown."""
    serializer = MarkdownSerializer(human="Joe", assistant="Claude")

    messages = [
        Message(sender=Role.USER, content="Hello", created=datetime(2024, 1, 1, 12, 0, 0)),
        Message(sender=Role.ASSISTANT, content="Hi there!", created=datetime(2024, 1, 1, 12, 0, 1)),
    ]

    log = ActivityLog(
        source="test",
        title="Test Chat",
        created=datetime(2024, 1, 1, 12, 0, 0),
        messages=messages,
    )

    result = serializer.serialize(log)
    assert "# Test Chat" in result
    assert "## Joe" in result
    assert "## Claude" in result
    assert "Hello" in result
    assert "Hi there!" in result


def test_serialize_with_metadata():
    """Test serialization with metadata."""
    serializer = MarkdownSerializer()

    log = ActivityLog(
        source="test",
        title="Test",
        created=datetime(2024, 1, 1, 12, 0, 0),
        messages=[],
        metadata={"model": "gpt-4", "tokens": 100},
    )

    result = serializer.serialize(log)
    assert "---" in result
    assert "model: gpt-4" in result
    assert "tokens: 100" in result


def test_add_metadata_frontmatter():
    """Test adding metadata as frontmatter."""
    serializer = MarkdownSerializer()
    lines = []
    metadata = {"key": "value", "number": 42}

    serializer._add_metadata(lines, metadata, frontmatter=True)

    assert lines[0] == "---"
    assert "key: value" in lines
    assert "number: 42" in lines
    assert lines[-2] == "---"


def test_add_metadata_yaml_block():
    """Test adding metadata as YAML block."""
    serializer = MarkdownSerializer()
    lines = []
    metadata = {"key": "value"}

    serializer._add_metadata(lines, metadata, frontmatter=False)

    assert lines[0] == "```yaml"
    assert "key: value" in lines
    assert lines[-2] == "```"


def test_add_header():
    """Test adding header with attributes."""
    serializer = MarkdownSerializer()
    lines = []

    serializer._add_header(lines, "Title", level=2, created="2024-01-01")

    assert lines[0] == "## Title [created:: 2024-01-01]"


def test_path_generation(tmp_path):
    """Test path generation for activity logs."""
    store = ActivityLogDirectoryStore(root=tmp_path)

    date = datetime(2024, 6, 15, 14, 30, 0)
    path = store.path("claude", date, "Test Title")

    expected = tmp_path / "claude" / "2024" / "06" / "2024-06-15-test-title.md"
    assert path == expected


def test_path_generation_no_title(tmp_path):
    """Test path generation without title."""
    store = ActivityLogDirectoryStore(root=tmp_path)

    date = datetime(2024, 6, 15, 14, 30, 0)
    path = store.path("claude", date, None)

    expected = tmp_path / "claude" / "2024" / "06" / "2024-06-15.md"
    assert path == expected


def test_store_and_fetch(tmp_path):
    """Test storing activity log and checking file creation."""
    store = ActivityLogDirectoryStore(root=tmp_path)

    log = ActivityLog(
        source="test",
        title="Test Log",
        created=datetime(2024, 6, 15, 14, 30, 0),
        messages=[
            Message(
                sender=Role.USER,
                content="Test message",
                created=datetime(2024, 6, 15, 14, 30, 0),
            )
        ],
    )

    store.store(log)

    # Check that file was created
    expected_path = store.path("test", log.created, log.title)
    assert expected_path.exists()

    # Check content
    with open(expected_path, "r") as f:
        content = f.read()
        assert "Test Log" in content
        assert "Test message" in content


def test_fetch_returns_file_paths(tmp_path):
    """Test that fetch method returns file paths in date range."""
    store = ActivityLogDirectoryStore(root=tmp_path)

    # Create test files in the expected directory structure
    test_dir = tmp_path / "test" / "2024" / "06"
    test_dir.mkdir(parents=True, exist_ok=True)

    # Create files with date-based names
    file1 = test_dir / "2024-06-15-log-1.md"
    file2 = test_dir / "2024-06-16-log-2.md"
    file3 = test_dir / "2024-06-17-log-3.md"

    # Write minimal markdown content
    file1.write_text("# Log 1\n\nTest content")
    file2.write_text("# Log 2\n\nTest content")
    file3.write_text("# Log 3\n\nTest content")

    # Test fetch method
    start = datetime(2024, 6, 15)
    end = datetime(2024, 6, 16)

    files = store.fetch(start, end)

    # Should return 2 Path objects in the date range
    assert len(files) == 2
    assert all(isinstance(f, Path) for f in files)

    # Verify correct files were found
    found_names = [f.name for f in files]
    assert "2024-06-15-log-1.md" in found_names
    assert "2024-06-16-log-2.md" in found_names
    assert "2024-06-17-log-3.md" not in found_names


def test_fetch_with_source_filter(tmp_path):
    """Test source filtering in fetch method."""
    store = ActivityLogDirectoryStore(root=tmp_path)

    # Create test files in different source directories
    claude_dir = tmp_path / "claude" / "2024" / "06"
    gemini_dir = tmp_path / "gemini" / "2024" / "06"
    claude_dir.mkdir(parents=True, exist_ok=True)
    gemini_dir.mkdir(parents=True, exist_ok=True)

    claude_file = claude_dir / "2024-06-15-claude-chat.md"
    gemini_file = gemini_dir / "2024-06-15-gemini-chat.md"

    claude_file.write_text("# Claude chat")
    gemini_file.write_text("# Gemini chat")

    # Test source filtering
    start = datetime(2024, 6, 15)
    end = datetime(2024, 6, 15)

    # Should only find claude files with filter
    claude_files = store.fetch(start, end, sources=["claude"])
    assert len(claude_files) == 1
    assert "claude" in str(claude_files[0])

    # Should find both files without filter
    all_files = store.fetch(start, end)
    assert len(all_files) == 2


def test_rglob_finds_nested_files(tmp_path):
    """Test that rglob correctly finds files in nested directory structure."""
    store = ActivityLogDirectoryStore(root=tmp_path)

    # Create nested directory structure as used by the app
    nested_dir = tmp_path / "claude" / "2024" / "06"
    nested_dir.mkdir(parents=True, exist_ok=True)

    deeper_dir = tmp_path / "claude" / "2024" / "07"
    deeper_dir.mkdir(parents=True, exist_ok=True)

    # Create test files
    file1 = nested_dir / "2024-06-15-test.md"
    file2 = deeper_dir / "2024-07-15-test.md"

    file1.write_text("# Test 1")
    file2.write_text("# Test 2")

    # Test that rglob finds both files
    found_files = []
    for source_dir in store.root.iterdir():
        if source_dir.is_dir():
            for md_file in source_dir.rglob("*.md"):
                found_files.append(md_file)

    assert len(found_files) == 2

    # Verify both paths are found
    file_names = [f.name for f in found_files]
    assert "2024-06-15-test.md" in file_names
    assert "2024-07-15-test.md" in file_names
