import email
import logging
import multiprocessing as mp
import smtplib
from contextlib import ContextDecorator
from dataclasses import asdict, dataclass
from logging.handlers import (QueueHandler, QueueListener,
                              TimedRotatingFileHandler)
from pathlib import Path
from typing import (Any, Callable, Dict, List, Literal, Optional, ParamSpec,
                    Tuple, TypeAlias, TypeVar, Union)

import jinja2
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database
from pymongo.errors import ServerSelectionTimeoutError

from .configuration import MongoConfig

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


def handle_shared_log_message(msg: SharedLogMessage) -> None:
    """Apply the logging config in msg and handle the record."""
    if msg.config is not None:
        logging.config.dictConfig(msg.config)
    if msg.record is not None:
        logging.getLogger(msg.record.name).handle(msg.record)


class SharedLogHandler(logging.handlers.QueueHandler):
    """Serialize and enqueue LogRecords."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = SharedLogMessage(record=self.prepare(record), config=None)
            self.enqueue(msg)
        except Exception:
            self.handleError(record)


class ReverseLogFilter(logging.Filter):
    """Filter out all records with loglevel greater than a specified base."""

    def __init__(self, level: LogLevel = logging.NOTSET) -> None:
        if isinstance(level, str):
            level = getattr(logging, level.upper())
        self.level = level

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno <= self.level


class TimedRotatingFileHandlerWithHeader(TimedRotatingFileHandler):
    """Add a header to a TimedRotatingFileHandler."""

    def __init__(self, filename: str, *args, **kwargs) -> None:
        self.header = kwargs.pop("header", None)
        path = Path(filename)
        if not path.parent.exists():
            path.parent.mkdir(parents=True)
        super().__init__(filename, *args, **kwargs)

    def _open(self):
        stream = super()._open()
        if self.header and stream.tell() == 0:
            stream.write(self.header + self.terminator)
            stream.flush()
        return stream


class BufferingSMTPHandler(logging.handlers.BufferingHandler):
    def __init__(
        self, mailhost, port, username, password, fromaddr, toaddrs, subject, capacity
    ):
        logging.handlers.BufferingHandler.__init__(self, capacity)
        self.mailhost = mailhost
        self.mailport = port
        self.username = username
        self.password = password
        self.fromaddr = fromaddr
        if isinstance(toaddrs, str):
            toaddrs = [toaddrs]
        self.toaddrs = toaddrs
        self.subject = subject
        self.setFormatter(logging.Formatter("%(asctime)s %(levelname)-5s %(message)s"))

    def flush(self):
        if len(self.buffer) > 0:
            try:
                smtp = smtplib.SMTP(self.mailhost, self.mailport)
                smtp.starttls()
                smtp.login(self.username, self.password)
                msg = "From: %s\r\nTo: %s\r\nSubject: %s\r\n\r\n" % (
                    self.fromaddr,
                    ",".join(self.toaddrs),
                    self.subject,
                )
                for record in self.buffer:
                    s = self.format(record)
                    msg = msg + s + "\r\n"
                smtp.sendmail(self.fromaddr, self.toaddrs, msg)
                smtp.quit()
            except Exception:
                if logging.raiseExceptions:
                    raise
            self.buffer = []


class MongoLogHandler(logging.handlers.BufferingHandler):
    """Basic logging facility for MongoDB.

    Based on the implementation in `log4mongo <https://github.com/log4mongo/log4mongo-python/>`_.
    """

    def __init__(
        self,
        mongo_config: MongoConfig,
        level: LogLevel = logging.NOTSET,
        buffer_size: int = -1,
        buffer_timeout: float = -1,
        raise_on_error: bool = True,
    ) -> None:
        super().__init__(level, buffer_size, buffer_timeout)
        self._collection, self._client, self._db = self._get_connection(mongo_config)

    def _get_connection(
        self, config: MongoConfig
    ) -> Tuple[Collection, MongoClient, Database]:
        client = MongoClient(
            host=config.host,
            port=config.port,
            username=config.username,
            password=config.password,
            authSource=config.authentication_db,
        )
        try:
            if not client.is_primary:
                raise ValueError("Configured MongoDB server cannot accept writes")
        except ServerSelectionTimeoutError:
            if not self.raise_on_error:
                return
            raise
        if config.collection is None:
            raise ValueError("A logging collection must be specified")
        db = client[config.database_name]
        collection = db[config.collection]
        return collection, client, db

    def close(self):
        ...

    def emit_many(self, records: List[logging.LogRecord]) -> None:
        if self._collection is not None:
            self._collection.insert_many(self._buffer)
