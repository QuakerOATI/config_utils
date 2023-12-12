import configparser
import json
import logging
import threading
import time
from abc import ABC, abstractmethod
from logging.handlers import TimedRotatingFileHandler
from queue import Queue
from typing import (Any, Callable, List, Literal, Tuple, TypeAlias, TypeVar,
                    Union)

import rich
import yaml
from pymongo import MongoClient
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
    def __init__(
        self,
        mongo_config: MongoConfig,
        buffer_size: int = -1,
        buffer_timeout: float = -1,
        raise_on_error: bool = True,
    ) -> None:
        super().__init__(buffer_size, buffer_timeout)
        self._collection, self._client, self._db = self._get_connection(mongo_config)

    def _get_connection(
        self, config: MongoConfig
    ) -> Tuple[
        pymongo.collection.Collection, pymongo.MongoClient, pymongo.database.Database
    ]:
        client = pymongo.MongoClient(
            host=mongo_config.host,
            port=mongo_config.port,
            username=mongo_config.username,
            password=mongo_config.password,
            authSourth=mongo_config.authentication_db,
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
