"""Chunking implementations for splitting notes into searchable pieces."""

import re
from typing import Iterator

from commonplace._search._types import Chunk
from commonplace._types import Note


class MarkdownChunker:
    """
    Chunks markdown documents by headers.

    Splits on header boundaries (##, ###, etc.) and preserves
    the hierarchical section path for context. Large sections are
    further split to stay within model context windows.
    """

    def __init__(
        self,
        max_chunk_chars: int = 1024,  # ~256 tokens for sentence transformers
        overlap_chars: int = 200,  # ~50 token overlap
    ):
        """
        Initialize the chunker.

        Args:
            max_chunk_chars: Maximum characters per chunk before splitting
            overlap_chars: Characters to overlap between split chunks
        """
        self.max_chunk_chars = max_chunk_chars
        self.overlap_chars = overlap_chars

    def chunk(self, note: Note) -> Iterator[Chunk]:
        """
        Split a markdown note into chunks by headers.

        Args:
            note: The note to chunk

        Yields:
            Chunks extracted from the note, one per section
        """
        lines = note.content.split("\n")
        current_section: list[str] = []
        current_text: list[str] = []
        chunk_start_offset = 0
        offset = 0

        for line in lines:
            # Check if this is a header line
            header_match = re.match(r"^(#{1,6})\s+(.+?)(?:\s+\[.*\])?$", line)

            if header_match:
                # Yield previous chunk if we have content
                if current_text and any(t.strip() for t in current_text):
                    yield from self._split_if_needed(note, current_section, current_text, chunk_start_offset)

                # Update section hierarchy
                level = len(header_match.group(1))
                header_text = header_match.group(2).strip()

                # Trim section stack to current level
                current_section = current_section[: level - 1]
                current_section.append(header_text)

                # Start new chunk - offset points to the header itself
                current_text = []
                chunk_start_offset = offset
            else:
                # Accumulate content
                current_text.append(line)

            offset += len(line) + 1  # +1 for newline

        # Yield final chunk if we have content
        if current_text and any(t.strip() for t in current_text):
            yield from self._split_if_needed(note, current_section, current_text, chunk_start_offset)

    def _split_if_needed(
        self, note: Note, section_stack: list[str], text_lines: list[str], start_offset: int
    ) -> Iterator[Chunk]:
        """
        Split a section into multiple chunks if it exceeds max_chunk_chars.

        Args:
            note: The note being chunked
            section_stack: Hierarchical section path
            text_lines: Lines of text in the section
            start_offset: Character offset where this section begins

        Yields:
            One or more chunks, split as needed to fit within size limits
        """
        section_path = " / ".join(section_stack) if section_stack else note.repo_path.path.stem
        chunk_text = "\n".join(text_lines).strip()

        # If chunk fits within limit, yield as-is
        if len(chunk_text) <= self.max_chunk_chars:
            yield Chunk(
                repo_path=note.repo_path,
                text=chunk_text,
                section=section_path,
                offset=start_offset,
            )
            return

        # Split large chunk with overlap
        current_pos = 0
        while current_pos < len(chunk_text):
            # Extract chunk with max size
            end_pos = current_pos + self.max_chunk_chars
            sub_chunk = chunk_text[current_pos:end_pos]

            # Try to break at word boundary if not at end
            if end_pos < len(chunk_text):
                # Look for last space/newline in the chunk
                last_break = max(
                    sub_chunk.rfind(" "),
                    sub_chunk.rfind("\n"),
                )
                if last_break > self.max_chunk_chars // 2:  # Only break if we're past halfway
                    sub_chunk = sub_chunk[:last_break]
                    end_pos = current_pos + last_break

            yield Chunk(
                repo_path=note.repo_path,
                text=sub_chunk.strip(),
                section=section_path,
                offset=start_offset + current_pos,
            )

            # Move forward with overlap
            current_pos = end_pos - self.overlap_chars if end_pos < len(chunk_text) else end_pos

    @staticmethod
    def _create_chunk(note: Note, section_stack: list[str], text_lines: list[str], start_offset: int) -> Chunk:
        """Create a chunk from accumulated text."""
        section_path = " / ".join(section_stack) if section_stack else note.repo_path.path.stem
        chunk_text = "\n".join(text_lines).strip()

        return Chunk(
            repo_path=note.repo_path,
            text=chunk_text,
            section=section_path,
            offset=start_offset,
        )
