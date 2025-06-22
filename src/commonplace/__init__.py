import importlib.metadata
import logging

from commonplace._config import Config

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0+dev"  # Fallback for development mode

LOGGER = logging.getLogger("melange")

CONFIG = Config()  # type: ignore
