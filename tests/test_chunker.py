"""Tests for markdown chunking."""

from pathlib import Path

from commonplace._search._chunker import MarkdownChunker
from commonplace._types import Note


class TestMarkdownChunker:
    def test_basic_chunking(self):
        """Test chunking a simple markdown document."""
        note = Note(
            path=Path("test.md"),
            content="""# Main Title

Some intro text.

## Section 1

Content for section 1.

## Section 2

Content for section 2.

### Subsection 2.1

Nested content.
""",
        )

        chunker = MarkdownChunker()
        chunks = list(chunker.chunk(note))

        assert len(chunks) == 4

        # Check first chunk (intro)
        assert chunks[0].section == "Main Title"
        assert chunks[0].text == "Some intro text."
        assert chunks[0].path == Path("test.md")

        # Check second chunk
        assert chunks[1].section == "Main Title / Section 1"
        assert chunks[1].text == "Content for section 1."

        # Check third chunk
        assert chunks[2].section == "Main Title / Section 2"
        assert chunks[2].text == "Content for section 2."

        # Check nested chunk
        assert chunks[3].section == "Main Title / Section 2 / Subsection 2.1"
        assert chunks[3].text == "Nested content."

    def test_no_headers(self):
        """Test chunking document without headers."""
        note = Note(
            path=Path("test.md"),
            content="Just some plain text without headers.",
        )

        chunker = MarkdownChunker()
        chunks = list(chunker.chunk(note))

        assert len(chunks) == 1
        assert chunks[0].section == "test"
        assert chunks[0].text == "Just some plain text without headers."

    def test_empty_sections_skipped(self):
        """Test that sections with no content are skipped."""
        note = Note(
            path=Path("test.md"),
            content="""# Title

## Empty Section

## Section with content

Some text here.
""",
        )

        chunker = MarkdownChunker()
        chunks = list(chunker.chunk(note))

        assert len(chunks) == 1
        assert chunks[0].section == "Title / Section with content"

    def test_offset_calculation(self):
        """Test that character offsets are calculated correctly."""
        note = Note(
            path=Path("test.md"),
            content="# Title\n\nFirst.\n\n## Section\n\nSecond.",
        )

        chunker = MarkdownChunker()
        chunks = list(chunker.chunk(note))

        # First chunk starts at "# Title"
        assert chunks[0].offset == 0
        assert note.content[chunks[0].offset :].startswith("# Title")

        # Second chunk starts at "## Section"
        assert chunks[1].offset == 17
        assert note.content[chunks[1].offset :].startswith("## Section")

    def test_header_with_metadata(self):
        """Test that headers with metadata annotations are handled."""
        note = Note(
            path=Path("test.md"),
            content="""# Title [created:: 2024-01-01]

Content here.
""",
        )

        chunker = MarkdownChunker()
        chunks = list(chunker.chunk(note))

        assert len(chunks) == 1
        assert chunks[0].section == "Title"
