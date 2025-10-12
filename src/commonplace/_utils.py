"""
Utility functions for text processing and formatting.

Provides helper functions for truncating text and creating URL-friendly slugs.
"""

import re
import shlex
import subprocess
import tempfile
from pathlib import Path
from typing import Iterable, Optional, TypeVar

import llm
import yaml
from rich.progress import Progress, TextColumn

from commonplace import logger

T = TypeVar("T")


def batched(iterable: Iterable[T], batch_size: int) -> Iterable[list[T]]:
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


def progress_track(iterable: Iterable[T], description: str, total: int | None = None) -> Iterable[T]:
    """
    Track progress through an iterable with a Rich progress bar showing count.

    Args:
        iterable: The iterable to track
        description: Description to show in the progress bar
        total: Total number of items (optional, will try to get from len() if not provided)

    Yields:
        Items from the iterable
    """
    if total is None:
        try:
            total = len(iterable)  # type: ignore
        except TypeError:
            total = None  # Indeterminate progress

    with Progress(*Progress.get_default_columns(), TextColumn("[dim]{task.fields[item]}")) as progress:
        task = progress.add_task(description, total=total, item="")
        for item in iterable:
            progress.update(task, advance=1, item=str(item))
            yield item


def edit_in_editor(content: str, editor: str) -> Optional[str]:
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
    buffer = Path(tempfile.NamedTemporaryFile(prefix="commonplace", suffix=".md", delete=False).name)

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


def parse_frontmatter(content: str) -> tuple[dict, str]:
    """
    Parse YAML frontmatter from markdown content.

    Args:
        content: Markdown content that may contain frontmatter

    Returns:
        Tuple of (metadata dict, body content)
        If no frontmatter found, returns ({}, original content)

    Raises:
        yaml.YAMLError: If frontmatter exists but cannot be parsed
    """
    lines = content.split("\n")

    # Check if content starts with frontmatter delimiter
    if not lines or lines[0].strip() != "---":
        return {}, content

    # Find closing delimiter
    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break

    if end_idx is None:
        # No closing delimiter found
        return {}, content

    # Parse YAML between delimiters
    yaml_content = "\n".join(lines[1:end_idx])
    metadata = yaml.safe_load(yaml_content) or {}

    # Body is everything after the closing delimiter
    body = "\n".join(lines[end_idx + 1 :])

    return metadata, body


def merge_frontmatter(existing_content: str, new_metadata: dict) -> dict:
    """
    Merge new metadata with existing frontmatter, preserving user additions.

    Args:
        existing_content: Existing markdown content with frontmatter
        new_metadata: New metadata from importer (these keys will be updated)

    Returns:
        Merged metadata dict (existing preserved, new overwrites on key collision)

    Raises:
        yaml.YAMLError: If existing frontmatter cannot be parsed
    """
    existing_metadata, _ = parse_frontmatter(existing_content)

    # Merge: existing | new means new overwrites existing where keys overlap
    return existing_metadata | new_metadata
