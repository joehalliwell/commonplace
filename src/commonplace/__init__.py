"""
Commonplace: A personal knowledge management tool for AI conversations.

Transforms scattered AI chat exports into an organized, searchable digital commonplace book.
Supports importing from Claude, Gemini, and other AI providers into standardized markdown files.
"""

import importlib.metadata
import logging
from functools import lru_cache

from commonplace._config import Config

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0+dev"  # Fallback for development mode

logger = logging.getLogger("commonplace")


@lru_cache(maxsize=1)
def get_config() -> Config:
    """Get the global config instance, cached."""
    try:
        return Config()
    except Exception as e:
        logger.error(
            "Failed to load configuration. Please ensure COMMONPLACE_ROOT is set to a valid directory path.\n"
            "Example: export COMMONPLACE_ROOT=/home/user/commonplace"
        )
        raise SystemExit(1) from e
