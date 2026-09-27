"""
Configuration management for the commonplace application.

Defines the Config class for handling application settings from
environment variables and TOML config files.
"""

import getpass
import os
import tomllib
from pathlib import Path
from typing import Any

from platformdirs import user_config_dir
from pydantic import Field
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

DEFAULT_CONFIG = Path(user_config_dir("commonplace")) / "config.toml"
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
    Configuration for a commonplace repo. Each layer overrides the ones below it:
    1. Environment variables with COMMONPLACE_ prefix
    2. Per-repo commonplace config at ${REPO_ROOT}/.commonplace/config.toml
    3. Global commonplace config at ~/.config/commonplace/config.toml
    4. Built-in defaults
    """

    model_config = SettingsConfigDict(
        env_nested_delimiter="_",
        env_prefix="COMMONPLACE_",
    )

    user: str = Field(default=DEFAULT_NAME, description="Human-readable name for the user e.g., Joe")
    wrap: int = Field(default=80, description="Target characters per line for text wrapping")
    editor: str = Field(default=DEFAULT_EDITOR, description="Default editor for opening notes")
    auto_index: bool = Field(default=True, description="Automatically index notes when they are added")
    ua: str = Field(
        default=DEFAULT_UA,
        description="User-Agent sent by fetchers. Override if a provider's bot check starts rejecting the default",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Env beats init kwargs, which is where `load` puts the TOML files."""
        return env_settings, init_settings

    @classmethod
    def load(cls, repo_root: Path, global_file: Path | None = None) -> "Config":
        """Overlay the per-repo config file on the global one, beneath the environment."""
        files = [global_file or DEFAULT_CONFIG, repo_root / ".commonplace" / "config.toml"]
        settings: dict[str, Any] = {}
        for path in files:
            if path.is_file():
                settings |= tomllib.loads(path.read_text())
        return cls(**settings)
