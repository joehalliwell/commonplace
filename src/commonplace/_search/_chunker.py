"""Chunking implementations for splitting notes into searchable pieces."""

import re
from typing import Iterator

from commonplace._search._types import Chunk
from commonplace._types import Note


class MarkdownChunker:
    """
    Chunks markdown documents by headers.

    Splits on header boundaries (##, ###, etc.) and preserves
    the hierarchical section path for context.
    """

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
                    yield self._create_chunk(note, current_section, current_text, chunk_start_offset)

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
            yield self._create_chunk(note, current_section, current_text, chunk_start_offset)

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
