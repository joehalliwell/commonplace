import logging

from rich.logging import RichHandler

logger = logging.getLogger("commonplace")
logger.addHandler(RichHandler())
