"""
Configuration management for the commonplace application.

Defines the Config class for handling application settings from
environment variables, .env files, and direct instantiation.
"""

from pydantic import DirectoryPath, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    )

    root: DirectoryPath = Field(description="The root directory for storing commonplace data")
    wrap: int = Field(default=80, description="Target characters per line for text wrapping")
