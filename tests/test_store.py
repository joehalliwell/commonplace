from datetime import datetime

from commonplace._import import MarkdownSerializer
from commonplace._import._types import ActivityLog, Message, Role


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
