import logging
import smtplib
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from ssl import SSLContext
from typing import List, Optional, Tuple

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database
from pymongo.errors import ServerSelectionTimeoutError

from ..configuration import MongoConfig
from . import LogLevel, SharedLogMessage
from .filters import AttributeFilter
from .formatters import EmailFormatter


class SharedLogHandler(logging.handlers.QueueHandler):
    """Serialize and enqueue LogRecords."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = SharedLogMessage(record=self.prepare(record), config=None)
            self.enqueue(msg)
        except Exception:
            self.handleError(record)


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
        self,
        capacity: int,
        body_template: str,
        mime_type: str,
        mailhost: str,
        port: int,
        datefmt: Optional[str] = None,
        template_style: Optional[str] = "%",
        toAddrs: List[str] = (),
        ccAddrs: List[str] = (),
        bccAddrs: List[str] = (),
        subject: str = "",
        fromAddr: str = "",
        username: Optional[str] = None,
        password: Optional[str] = None,
        ssl_context: Optional[SSLContext] = None,
        attachment: Optional[str] = None,
    ) -> None:
        # parent class will automatically flush if buffer reaches capacity
        super().__init__(capacity)

        # the formatter will "own" the remaining constructor args
        self.mime_type = mime_type
        self.mailhost = mailhost
        self.mailport = port
        self.fromAddr = fromAddr
        self.toAddrs = toAddrs
        self.ccAddrs = ccAddrs
        self.bccAddrs = bccAddrs

        self._credentials = None
        if username is not None or password is not None:
            self._credentials = (username, password)

        self._ssl_context = ssl_context

        # only process records with "email" attribute
        self.addFilter(AttributeFilter("email"))
        self.setFormatter(
            EmailFormatter(
                body_template,
                datefmt,
                style=template_style,
                mime_type=mime_type,
                defaultFromAddr=fromAddr,
                defaultToAddrs=toAddrs,
                defaultSubject=subject,
                defaultCCAddrs=ccAddrs,
                defaultAttachment=attachment,
            )
        )

    def _get_smtp_connection(self):
        smtp = smtplib.SMTP(host=self.mailhost, port=self.mailport)
        if self._ssl_context is not None:
            smtp.starttls(context=self._ssl_context)
        if self._credentials is not None:
            smtp.login(*self.credentials)
        smtp.connect(host=self.mailhost, port=self.mailport)
        smtp.ehlo()
        return smtp

    def _get_sender(self, record: logging.LogRecord) -> str:
        return getattr(record, "fromAddr", self.fromAddr)

    def _get_recipients(self, record: logging.LogRecord) -> str:
        recipients = [
            *getattr(record, "toAddrs", self.toAddrs),
            *getattr(record, "ccAddrs", self.ccAddrs),
            *getattr(record, "bccAddrs", self.bccAddrs),
        ]
        return ",".join(recipients)

    def flush(self) -> None:
        if self.buffer:
            with self._get_smtp_connection() as smtp:
                while self.buffer:
                    try:
                        record = self.buffer.pop()
                        smtp.sendmail(
                            self._get_sender(record),
                            self._get_recipients(record),
                            self.format(record),
                        )
                    except Exception:
                        if logging.raiseExceptions:
                            raise


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
