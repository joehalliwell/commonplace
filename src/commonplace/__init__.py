"""
Commonplace: A personal knowledge management tool for AI conversations.

Transforms scattered AI chat exports into an organized, searchable digital commonplace book.
Supports importing from Claude, Gemini, and other AI providers into standardized markdown files.
"""

import importlib.metadata

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0+dev"  # Fallback for development mode
