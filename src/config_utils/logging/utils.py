import logging
import multiprocessing as mp
from contextlib import ContextDecorator
from typing import Union

from .types import LogLevel


def get_loglevel(level: Union[str, int]) -> LogLevel:
    """Convenience function to get loglevel name.

    Exceptions raised by the logging module's lookup methods are caught, so
    barring exceptions raised by the level parameter itself, this function
    should never raise.

    Args:
        level: name of loglevel or numerical value
    """
    try:
        if isinstance(level, str):
            level = logging._checkLevel(level.upper())
        return logging._levelToName[level]
    except (ValueError, KeyError):
        return "NOTSET"


class log_from_mp(ContextDecorator):
    """Write log messages from multiprocessing module to stderr.

    This class can be used as either a context manager or a decorator.
    """

    def __init__(self, level=logging.INFO):
        """
        Args:
            level: loglevel to set on the multiprocessing module logger
        """
        self.level = level

    def __enter__(self):
        mp.log_to_stderr(level=self.level)

    def __exit__(self, exc_type, exc, exc_tb):
        mp_logger = mp.get_logger()
        for h in mp_logger.handlers:
            mp_logger.removeHandler(h)
