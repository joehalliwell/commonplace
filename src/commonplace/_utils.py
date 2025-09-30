"""
Utility functions for text processing and formatting.

Provides helper functions for truncating text and creating URL-friendly slugs.
"""

import re
from typing import Iterable, TypeVar

import llm
from rich.progress import Progress

from commonplace import logger

T = TypeVar("T")


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

    with Progress() as progress:
        task = progress.add_task(description, total=total)
        for item in iterable:
            yield item
            progress.advance(task)
