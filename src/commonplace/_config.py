"""
Configuration management for the commonplace application.

Defines the Config class for handling application settings from
environment variables, .env files, and direct instantiation.
"""

import getpass
import os
from pathlib import Path

from platformdirs import user_config_dir
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_CONFIG = Path(user_config_dir("commonplace")) / "commonplace.toml"
DEFAULT_NAME = getpass.getuser().title()  # Get the current user's name for default human-readable name
DEFAULT_EDITOR = os.getenv("EDITOR", default="vim")

# A full, current Chrome UA — every provider fronts its internal API with a bot
# check that a terse or stale one fails. Cloudflare also binds `cf_clearance` to
# the User-Agent that solved the challenge, so one far from the user's real
# browser risks the cookie being read as replayed. Bump when Chrome moves on;
# override via COMMONPLACE_UA if a provider starts rejecting it before we do.
DEFAULT_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"


class Config(BaseSettings):
    """
    Configuration for a commonplace repo. This should be the result of several overlays:
    1. Built-in defaults
    2. Environment variables with COMMONPLACE_ prefix
    3. Global commonplace config at ~/.config/commonplace/config.toml
    4. Per-repo commonplace config at ${REPO_ROOT}/.commonplace/config.toml
    """

    model_config = SettingsConfigDict(
        env_nested_delimiter="_",
        env_prefix="COMMONPLACE_",
        toml_file=DEFAULT_CONFIG,
    )

    user: str = Field(default=DEFAULT_NAME, description="Human-readable name for the user e.g., Joe")
    wrap: int = Field(default=80, description="Target characters per line for text wrapping")
    editor: str = Field(default=DEFAULT_EDITOR, description="Default editor for opening notes")
    auto_index: bool = Field(default=True, description="Automatically index notes when they are added")
    ua: str = Field(
        default=DEFAULT_UA,
        description="User-Agent sent by fetchers. Override if a provider's bot check starts rejecting the default",
    )
