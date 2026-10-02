"""
Utility functions for text processing and formatting.

Provides helper functions for truncating text and creating URL-friendly slugs.
"""

import re
import shlex
import subprocess
import tempfile
from collections.abc import Iterable
from pathlib import Path

import llm
import yaml

from commonplace._logging import logger


def batched[T](iterable: Iterable[T], batch_size: int) -> Iterable[list[T]]:
    """
    Batch an iterable into chunks of specified size.

    Args:
        iterable: The iterable to batch
        batch_size: Number of items per batch

    Yields:
        Lists of items, each containing up to batch_size items
    """
    batch = []
    for item in iterable:
        batch.append(item)
        if len(batch) >= batch_size:
            yield batch
            batch = []

    # Yield remaining items
    if batch:
        yield batch


def truncate(text: str, max_length: int = 200) -> str:
    """
    Truncate text to a maximum length, adding a suffix indicating how much was cut.

    Args:
        text: The text to truncate
        max_length: Maximum length before truncation (default: 200)

    Returns:
        The original text if under max_length, otherwise truncated text with suffix
    """
    if len(text) > max_length:
        return text[:max_length] + f" (+{len(text) - max_length} more)"
    return text


def slugify(text: str) -> str:
    """
    Convert text to a URL-friendly slug.

    Args:
        text: The text to slugify

    Returns:
        A lowercase string with spaces replaced by hyphens and
        non-alphanumeric characters removed
    """
    text = text.lower()
    text = text.replace(" ", "-")
    slug = re.sub("[^a-z0-9-]", "", text)
    return slug


def get_model(model_name: str) -> llm.Model:
    """Get the configured LLM model, with helpful help."""
    try:
        return llm.get_model(model_name)

    except Exception as e:
        logger.error(f"Failed to load model '{model_name}': {e}")
        logger.info(f"Pick: {llm.get_models()}")
        logger.info("Make sure the model is installed and configured. Try: llm models list")
        raise


def edit_in_editor(content: str, editor: str) -> str | None:
    """
    Open content in an editor for editing.

    Args:
        content: The initial content to edit
        editor: Path to the editor executable

    Returns:
        Edited content if changes were made, None if no changes

    Raises:
        subprocess.CalledProcessError: If editor exits with non-zero status
        FileNotFoundError: If editor executable is not found
    """
    # The file must outlive this scope for the editor to open it; the
    # `finally: buffer.unlink()` below is the close.
    buffer = Path(tempfile.NamedTemporaryFile(prefix="commonplace", suffix=".md", delete=False).name)  # noqa: SIM115

    try:
        buffer.write_text(content, encoding="utf-8")

        logger.info(f"Waiting for edits on {buffer}")
        subprocess.run([*shlex.split(editor), str(buffer)], check=True)

        edited_content = buffer.read_text(encoding="utf-8")

        # If there were no edits, return None
        if edited_content == content:
            logger.info("No edits")
            return None

        return edited_content

    finally:
        buffer.unlink()


def load_frontmatter(content: str) -> tuple[dict, str]:
    """
    Parse YAML frontmatter from markdown content.

    Args:
        content: Markdown content that may contain frontmatter

    Returns:
        Tuple of (metadata dict, body content)
        If no frontmatter found, or what is there is not a YAML mapping,
        returns ({}, original content)
    """
    lines = content.split("\n")

    # Check if content starts with frontmatter delimiter
    if not lines or lines[0].strip() != "---":
        return {}, content

    # Find closing delimiter
    end_idx = None
    for i in range(1, len(lines)):
        # Unindented only: a `---` inside a multi-line value is indented.
        if lines[i].rstrip() == "---":
            end_idx = i
            break

    if end_idx is None:
        # No closing delimiter found
        return {}, content

    # Parse YAML between delimiters
    yaml_content = "\n".join(lines[1:end_idx])
    try:
        metadata = yaml.safe_load(yaml_content) or {}
    except yaml.YAMLError:
        return {}, content
    if not isinstance(metadata, dict):
        # A rule, some prose and another rule: any markdown file may open that way.
        return {}, content

    # Body is everything after the closing delimiter and the blank line `dump_frontmatter` puts there
    body_lines = lines[end_idx + 1 :]
    if len(body_lines) > 1 and not body_lines[0]:
        body_lines = body_lines[1:]

    return metadata, "\n".join(body_lines)


def dump_frontmatter(metadata: dict, body: str) -> str:
    """Markdown content from its parts: the inverse of `load_frontmatter`."""
    if not metadata:
        return body
    dumped = yaml.safe_dump(metadata, sort_keys=False, allow_unicode=True, width=float("inf"))
    return f"---\n{dumped}---\n\n{body}"


def sniff_gzipped_jsonl(path: Path) -> dict | None:
    """Peek at the first JSON object in a gzipped JSONL file.

    Returns None if the file isn't a valid `.jsonl.gz`, the first line isn't
    JSON, or that JSON isn't a dict. Used by importers to identify their own
    fetcher output vs. arbitrary .jsonl.gz files."""
    import gzip
    import json

    if not path.name.endswith(".jsonl.gz"):
        return None
    try:
        with gzip.open(path, "rt", encoding="utf-8") as f:
            first = f.readline()
        entry = json.loads(first)
    except Exception:  # noqa: BLE001 - probing an arbitrary file; any failure means "not ours"
        return None
    return entry if isinstance(entry, dict) else None
