"""Tests for markdown chunking."""

from pathlib import Path

from commonplace._search._chunker import MarkdownChunker


def test_basic_chunking(make_note):
    """Test chunking a simple markdown document."""
    note = make_note(
        path="test.md",
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
    assert chunks[0].repo_path.path == Path("test.md")

    # Check second chunk
    assert chunks[1].section == "Main Title / Section 1"
    assert chunks[1].text == "Content for section 1."

    # Check third chunk
    assert chunks[2].section == "Main Title / Section 2"
    assert chunks[2].text == "Content for section 2."

    # Check nested chunk
    assert chunks[3].section == "Main Title / Section 2 / Subsection 2.1"
    assert chunks[3].text == "Nested content."


def test_no_headers(make_note):
    """Test chunking document without headers."""
    note = make_note(
        path="test.md",
        content="Just some plain text without headers.",
    )

    chunker = MarkdownChunker()
    chunks = list(chunker.chunk(note))

    assert len(chunks) == 1
    assert chunks[0].section == "test"
    assert chunks[0].text == "Just some plain text without headers."


def test_empty_sections_skipped(make_note):
    """Test that sections with no content are skipped."""
    note = make_note(
        path="test.md",
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


def test_offset_calculation(make_note):
    """Test that character offsets are calculated correctly."""
    note = make_note(
        path="test.md",
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


def test_header_with_metadata(make_note):
    """Test that headers with metadata annotations are handled."""
    note = make_note(
        path="test.md",
        content="""# Title [created:: 2024-01-01]

Content here.
""",
    )

    chunker = MarkdownChunker()
    chunks = list(chunker.chunk(note))

    assert len(chunks) == 1
    assert chunks[0].section == "Title"


def test_large_section_splitting(make_note):
    """Test that large sections are split into multiple chunks."""
    # Create a section with 2000 characters of content
    large_content = " ".join([f"Word{i}" for i in range(300)])  # ~2000 chars

    note = make_note(
        path="test.md",
        content=f"""# Title

## Large Section

{large_content}
""",
    )

    chunker = MarkdownChunker(max_chunk_chars=500, overlap_chars=50)
    chunks = list(chunker.chunk(note))

    # Should have at least 3 chunks: small intro + multiple from large section
    assert len(chunks) >= 3

    # All chunks from the large section should have the same section path
    large_section_chunks = [c for c in chunks if c.section == "Title / Large Section"]
    assert len(large_section_chunks) >= 2

    # Each chunk should be within size limit (with some margin for word breaks)
    for chunk in large_section_chunks:
        assert len(chunk.text) <= 550  # Allow some overage for word boundary

    # Check that chunks have overlap - last words of one chunk should appear in next
    if len(large_section_chunks) >= 2:
        first_chunk_end = large_section_chunks[0].text.split()[-5:]  # Last 5 words
        second_chunk_start = large_section_chunks[1].text.split()[:20]  # First 20 words
        # At least one word should overlap
        assert any(word in second_chunk_start for word in first_chunk_end)


def test_small_sections_not_split(make_note):
    """Test that sections under the size limit are not split."""
    note = make_note(
        path="test.md",
        content="""# Title

## Section 1

Short content here.

## Section 2

Also short.
""",
    )

    chunker = MarkdownChunker(max_chunk_chars=500, overlap_chars=50)
    chunks = list(chunker.chunk(note))

    # Should have 2 chunks, one for each section (intro is empty)
    assert len(chunks) == 2
    assert chunks[0].section == "Title / Section 1"
    assert chunks[1].section == "Title / Section 2"
    assert chunks[0].text == "Short content here."
    assert chunks[1].text == "Also short."
