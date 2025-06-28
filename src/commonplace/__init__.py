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
    return Config()
