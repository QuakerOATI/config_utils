import logging
import multiprocessing as mp
from contextlib import ContextDecorator
from dataclasses import dataclass
from typing import Dict, Literal, TypeAlias, Union

LogLevel: TypeAlias = Union[
    Literal[
        "DEBUG",
        "INFO",
        "WARNING",
        "ERROR",
        "CRITICAL",
        "FATAL",
        "NOTSET",
    ],
    int,
]


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


@dataclass
class SharedLogMessage:
    record: logging.LogRecord
    config: Dict
