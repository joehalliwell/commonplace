"""
Configuration management for the commonplace application.

Defines the Config class for handling application settings from
environment variables, .env files, and direct instantiation.
"""

import getpass
import os
from pathlib import Path

from platformdirs import user_config_dir, user_cache_dir
from pydantic import DirectoryPath, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from commonplace._types import RepoPath

DEFAULT_CONFIG = Path(user_config_dir("commonplace")) / "commonplace.toml"
DEFAULT_CACHE = Path(user_cache_dir("commonplace", ensure_exists=True))
DEFAULT_NAME = getpass.getuser().title()  # Get the current user's name for default human-readable name
DEFAULT_EDITOR = os.getenv("EDITOR", default="vim")


class Config(BaseSettings):
    """
    Configuration settings for the commonplace application.

    Settings can be provided via:
    - Environment variables (prefixed with COMMONPLACE_)
    - .env file in the current directory
    - Direct instantiation with keyword arguments

    Example:
        # Via environment variable
        export COMMONPLACE_ROOT=/home/user/commonplace

        # Via .env file
        COMMONPLACE_ROOT=/home/user/commonplace
        COMMONPLACE_WRAP=120
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="_",
        env_prefix="COMMONPLACE_",
        toml_file=DEFAULT_CONFIG,
    )

    root: DirectoryPath = Field(
        description="The root directory for storing commonplace data",
    )
    cache: DirectoryPath = Field(
        default=Path(user_cache_dir("commonplace", ensure_exists=True)),
        description="Cache directory",
    )
    user: str = Field(default=DEFAULT_NAME, description="Human-readable name for the user e.g., Joe")
    wrap: int = Field(default=80, description="Target characters per line for text wrapping")
    editor: str = Field(default=DEFAULT_EDITOR, description="Default editor for opening notes")

    @field_validator("root", mode="before")
    @classmethod
    def validate_root_not_empty(cls, v):
        if isinstance(v, str) and v.strip() == "":
            raise ValueError("Root path cannot be empty")
        return v

    @model_validator(mode="before")
    def defaults_based_on_root(cls, values):
        """
        Set default values based on the root directory.
        If root is a string, convert it to a Path object.
        """
        return values

    def get_repo(self):
        """Get the Commonplace repository at the root path."""
        from commonplace._repo import Commonplace

        return Commonplace.open(self.root)

    def get_index(self):
        """Get the search index."""
        from commonplace._search._sqlite import SQLiteSearchIndex
        from commonplace._search._embedder import SentenceTransformersEmbedder

        embedder = SentenceTransformersEmbedder()
        return SQLiteSearchIndex(self.cache / "index.db", embedder=embedder)

    def source(self, repo_path: RepoPath) -> str:
        """The source of this collection of notes/chats"""
        parts = repo_path.path.parts
        if len(parts) < 2:
            return "misc"
        if parts[0] == "chats":
            return "/".join(parts[:2])
        return parts[0]


if __name__ == "__main__":
    print(Config.model_validate({}))
