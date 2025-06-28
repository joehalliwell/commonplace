import importlib.metadata
import logging
from functools import lru_cache

from commonplace._config import Config

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0+dev"  # Fallback for development mode

LOGGER = logging.getLogger("commonplace")


@lru_cache(maxsize=1)
def get_config() -> Config:
    """Get the global config instance, cached."""
    try:
        return Config()
    except Exception as e:
        LOGGER.error(
            "Failed to load configuration. Please ensure COMMONPLACE_ROOT is set to a valid directory path.\n"
            "Example: export COMMONPLACE_ROOT=/home/user/commonplace"
        )
        raise SystemExit(1) from e
