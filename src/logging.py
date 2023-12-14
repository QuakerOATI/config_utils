import logging
import multiprocessing as mp
import threading
import time
from logging.handlers import (QueueHandler, QueueListener,
                              TimedRotatingFileHandler)
from pathlib import Path
from typing import (Any, Callable, List, Literal, Optional, Tuple, TypeAlias,
                    TypeVar, Union)

import rich
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
    ],
    int,
]

_manager = None


def setup_logging(manager: Optional[mp.Manager]) -> None:
    global _manager
    if _manager is None:
        _manager = manager


def _filter_loglevels_inverse(
    loglevel: LogLevel,
) -> Callable[[logging.LogRecord], bool]:
    """Logging filter factory"""
    level = getattr(logging, loglevel)

    def filter(record: logging.LogRecord) -> bool:
        return record.level <= level

    return filter


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


class BatchableLogHandler(logging.Handler):
    """Base class for a handler that can emit LogRecords in batches."""

    def __init__(
        self,
        level: LogLevel = logging.NOTSET,
        buffer_size: int = -1,
        buffer_timeout: float = -1,
    ) -> None:
        super().__init__(level)
        self._buffer = []
        self._buffer_size = buffer_size
        self._buffer_lock = threading.RLock()
        self._buffer_timeout = buffer_timeout
        self._last_record = None
        self._last_emitted = None

    def emit_one(self, record: logging.LogRecord) -> None:
        self._last_emitted = time.time()
        super().emit(record)

    def emit_many(self, records: List[logging.LogRecord]) -> None:
        self._last_emitted = time.time()
        for record in records:
            self.emit_one(record)

    def emit(self, record: logging.LogRecord) -> None:
        with self._buffer_lock:
            self._last_record = record
            self._buffer.append(self.format(record))

        if (
            len(self._buffer) > self._buffer_size
            and time.time() - self._last_emitted >= self._buffer_timeout
        ):
            self.flush()

    def flush(self) -> None:
        if self._buffer:
            with self._buffer_lock:
                try:
                    self.emit_many(self._buffer)
                    self.clear()
                except Exception:
                    self.handleError(self._last_record)

    def clear(self) -> None:
        del self._buffer
        self._buffer = []


class MongoLogHandler(BatchableLogHandler):
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


class AsyncLoggerFactory:
    def __init__(self, *handlers):
        ...


def get_mp_logger(handler):
    queue = mp.Queue(-1)
    proxy_handler = QueueHandler(queue)
    listener = QueueListener(queue)


SENTINEL = object()
_mp_log_handlers = {}
_mp_logger = mp.log_to_stderr(level=logging.WARNING)


def register_mp_log_handler(handler: logging.LogHandler, handler_name: str) -> None:
    queue = mp.Queue(-1)

    def listener():
        while True:
            record = queue.get()
            try:
                if record is SENTINEL:
                    break
                logger = logging.getLogger(record.name)
                logger.handle(record)
            except Exception:
                logging.getLogger().exception(
                    f"Exception in listener process for multiprocessing log handler {handler_name}"
                )
