import logging
import multiprocessing as mp
import platform
import smtplib
import textwrap
from contextlib import ContextDecorator
from dataclasses import asdict, dataclass
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from logging.handlers import (QueueHandler, QueueListener,
                              TimedRotatingFileHandler)
from pathlib import Path
from ssl import SSLContext, _create_stdlib_context
from typing import (Any, Callable, Dict, Iterable, List, Literal, Mapping,
                    Optional, ParamSpec, Tuple, TypeAlias, TypeVar, Union)

import jinja2
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database
from pymongo.errors import ServerSelectionTimeoutError

from .configuration import MongoConfig
from .file_utils import resolve_path

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


class MessageTypeAdapter(logging.LoggerAdapter):
    """Treat unexpected kwargs in logging methods like "extra" args.

    Logging methods accept a keyword argument "extra" whose value should be a
    dict containing extra contextual information to be added to the LogRecord.
    This adapter stores a list of extra keys to expect and automatically adds
    them to the LogRecord as attributes without having to include them in an
    "extra" dict.  The advantage of this is that custom handlers can then
    format messages which reference these custom keys.

    For example:
    >>> app_logger = MessageTypeLoggingAdapter(logging.getLogger(), "email")
    >>> app_logger.info("This message will be logged normally")
    >>> app_logger.info(
    ...     "This message will produce a LogRecord with attribute 'email' = 'foo'",
    ...     email="foo"
    ... )
    """

    def __init__(
        self, logger: logging.Logger, *keys: List[str], **kwargs: Dict
    ) -> None:
        """
        Args:
            logger: logger instance to wrap
            *keys: list of strings to treat as "extra" args in logging methods
            **kwargs: dict of any extra contextual information to include with
                LogRecords processed by this adapter
        """
        self.message_type_keys = keys
        super().__init__(logger, kwargs)

    def process(self, msg: str, kwargs: Dict) -> Tuple[str, Dict]:
        extra = kwargs.setdefault("extra", {})
        extra.update(self.extra)
        for k in self.message_type_keys:
            kwargs["extra"][k] = kwargs.pop(k, None)
        return msg, kwargs


class AttributeFilter(logging.Filter):
    """Check if LogRecord has a given attribute.

    The intended use-case is to check for attributes included in the record
    via the logging methods' "extra" parameter.  For example, a custom SMTP
    handler could filter for LogRecords containing an "email" attribute
    pointing to a dict containing email data (sender, recipient, subject,
    etc.).

    If a record contains the target attribute, and if its value is a Mapping,
    then the filter will modify the record's __dict__ in-place with the
    key-value pairs in the target attribute.  This is done in order to allow
    formatter template strings to reference keys contained in the target dict.
    """

    def __init__(self, attr_name: str) -> None:
        """
        Args:
            message_type: name of target message type
        """
        self.attr_name = attr_name

    def filter(self, record: logging.LogRecord) -> bool:
        msg_data = getattr(record, self.attr_name, None)
        if msg_data is not None:
            # add dict keys to record instance so they can be referenced in templates
            # TODO: think of a better way to do this
            if isinstance(msg_data, dict):
                for k, v in msg_data.items():
                    setattr(record, k, v)
            return True
        return False


class EmailFormatter(logging.Formatter):
    """Format LogRecords as emails using data stored in "extra" record attrs.

    The formatter expects LogRecords to have an attribute "email"
    containing a Mapping of email-related data, in the following form:
        record.email = {
            "mime_type": str,
            "fromAddr": str,
            "toAddrs": List[str],
            "subject": str,
            "ccAddrs": List[str],
            "attachment": str,
            # more optional key-value pairs
        }
    The contructor takes optional default values for each key; individual
    records missing one or more keys will fall back to these defaults when
    formatted.

    This class is designed to be used with the BufferingSMTPHandler, which
    will automatically add an instance of EmailFormatter on construction.
    This class should therefore likely not be constructed directly.
    """

    def __init__(
        self,
        body_template: str = "%(message)s",
        datefmt: Optional[str] = None,
        style: Optional[str] = "%",
        mime_type: str = "text",
        defaultFromAddr: str = "",
        defaultToAddrs: Iterable[str] = (),
        defaultSubject: str = "",
        defaultCCAddrs: Iterable[str] = (),
        defaultAttachment: Optional[str] = None,
    ) -> None:
        super().__init__(body_template, datefmt, style)
        self.mime_type = mime_type
        self.defaults = {
            "subject": defaultSubject,
            "fromAddr": defaultFromAddr,
            "toAddrs": defaultToAddrs,
            "ccAddrs": defaultCCAddrs,
            "attachment": defaultAttachment,
        }

    def format(self, record: logging.LogRecord) -> str:
        msg = MIMEMultipart()
        msg_data = getattr(record, "email", {})
        msg["From"] = msg_data.get("fromAddr", self.defaults["fromAddr"])
        msg["Subject"] = msg_data.get("subject", self.defaults["subject"])

        # Don't include BCC addresses in the message (that's the whole point)
        msg["To"] = ", ".join(msg_data.get("toAddrs", self.defaults["toAddrs"]))
        msg["Cc"] = ", ".join(msg_data.get("ccAddrs", self.defaults["ccAddrs"]))

        attachment = msg_data.get("attachment", self.defaults["attachment"])
        if attachment is not None:
            file = resolve_path(attachment)
            attachment = MIMEBase("application", "octet-stream")
            attachment.set_payload(file.read_bytes())
            encoders.encode_base64(attachment)
            attachment.add_header(
                "Content-Disposition", f"attachment; filename = {file}"
            )
            msg.attach(attachment)
        msg.attach(MIMEText(super().format(record), self.mime_type))
        return msg.as_string()


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
