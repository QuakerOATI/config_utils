import logging
import multiprocessing as mp
import sys
import threading
from contextlib import ContextDecorator
from logging.config import dictConfig
from pathlib import Path
from typing import Callable, Dict, Literal, Optional, TypeAlias, Union

from .config_utils import get_config
from .log_utils import (LogLevel, ReverseLogFilter,
                        TimedRotatingFileHandlerWithHeader)

_LOGGING_ROOT = Path(get_config("log_dir"))
if not _LOGGING_ROOT.is_absolute():
    from . import PROJECT_ROOT

    _LOGGING_ROOT = PROJECT_ROOT.joinpath(_LOGGING_ROOT)

LOGFILE_COLUMNS = (
    ("LEVEL", "%(levelname)s"),
    ("DATETIME", "%(asctime)s"),
    ("LOGGER", "%(name)s"),
    ("MESSAGE", "%(message)s"),
    ("MODULE", "%(module)s"),
    ("FILENAME", "%(filename)s"),
    ("FUNCTION", "%(funcname)s"),
    ("LINENO", "%(lineno)s"),
    ("THREAD", "%(threadName)s:%(thread)d"),
    ("PID", "%(process)d"),
)

_CONFIG_DICT = {
    "version": 1,
    "formatters": {
        "brief": "[%(levelname)-9.9s] %(name)-12.12s: %(asctime)s: $(message)s",
        "tsv": "\t".join(col[0] for col in LOGFILE_COLUMNS),
    },
    "filters": {
        "info_or_lower": {
            "()": "ext://config_utils.log_utils.ReverseLogFilter",
            "param": "INFO",
        }
    },
    "handlers": {
        "rich": {
            "class": "ext://rich.logging.RichHandler",
        },
        "stdout": {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
            "filters": ["info_or_lower"],
            "formatter": "brief",
            "level": "DEBUG",
        },
        "stderr": {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stderr",
            "formatter": "brief",
            "level": "ERROR",
        },
        "mongodb": {
            "class": "MongoLogHandler",
        },
        "email": {
            "class": "logging.handlers.SMTPHandler",
        },
    },
}


__LOGGING_QUEUE: Optional[mp.Queue] = None


class log_from_mp(ContextDecorator):
    def __init__(self, level=logging.INFO):
        self.level = level

    def __enter__(self):
        mp.log_to_stderr(level=self.level)

    def __exit__(self, exc_type, exc, exc_tb):
        mp_logger = mp.get_logger()
        for h in mp_logger.handlers:
            mp_logger.removeHandler(h)


class SharedLogHandler(logging.handlers.QueueHandler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = {SharedLogListener.RECORD: self.prepare(record)}
            self.enqueue(msg)
        except Exception:
            self.handleError(record)


class SharedLogListener(mp.Process):
    CONFIG: str = "CONFIG"
    RECORD: str = "RECORD"

    def __init__(
        self, queue: mp.Queue, init_logger: Callable[None, None], reraise: bool = True
    ) -> None:
        self.queue = queue
        self.stop_event = None
        self.init_logger = init_logger
        self.reraise = reraise
        super().__init__(
            target=self.listen,
            name=self.__class__.__name__,
            daemon=True,
        )

    def serve_forever(self):
        self.stop_event = mp.Event()
        self.init_logger()
        try:
            listener = threading.Thread(target=self.listen)
            listener.daemon = True
            listener.start()
            try:
                while not self.stop_event.is_set():
                    self.stop_event.wait(1)
            except (KeyboardInterrupt, SystemExit):
                pass
        finally:
            if sys.stdout != sys.__stdout__:
                sys.stdout = sys.__stdout__
                sys.stderr = sys.__stderr__
            sys.exit(0)

    def listen(self):
        while True:
            try:
                req = self.queue.get()  # don't use get_nowait, since it raises on empty
            except OSError:
                # not sure if this is really necessary here
                # TODO: check this (cf. mp.managers.Server.accepter implementation)
                continue
            except Exception:
                logging.getLogger(self.__class__.__name__).exception(
                    "Exception raised while handling a logging request", exc_info=True
                )
                if self.reraise:
                    raise
            t = threading.Thread(target=self.handle_request, args=(req,))
            t.daemon = True
            t.start()

    def handle_request(self, req: Dict) -> None:
        if self.CONFIG in req:
            dictConfig(req[self.CONFIG])
        if self.RECORD in req:
            logging.getLogger(req[self.RECORD].name).handle(req[self.RECORD])


def _configure_root_logger() -> None:
    pass


def _configure_sublogger(name: str, level: LogLevel = logging.NOTSET) -> None:
    logfile = _LOGGING_ROOT.joinpath(*(".".split(name)))
    if not logfile.parent.exists():
        logfile.parent.mkdir(parents=True)
    log_spec = {
        "handlers": ["file"],
        "level": level,
    }
    msg = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "brief": {
                "format": "[%(levelname)-9.9s] %(name)-12.12s: %(asctime)s: $(message)s"
            },
            "tsv": {
                "format": "[%(levelname)-9.9s] %(name)-12.12s: %(asctime)s: $(message)s"  # TODO: Change this
            },
        },
        "handlers": {
            "file": {
                "()": TimedRotatingFileHandlerWithHeader,
                "level": "DEBUG",
                "formatter": "tsv",
                "header": "LOG RECORDS\n===========\n",
                "filename": str(logfile),
            }
        },
        "loggers": {name: log_spec},
    }
    try:
        __LOGGING_QUEUE.put_nowait({SharedLogHandler.CONFIG: msg})
    except (mp.queues.Full, ValueError):
        # TODO: figure out something intelligent to do here
        raise


@log_from_mp(logging.INFO)
def init() -> None:
    global __LOGGING_QUEUE
    if __LOGGING_QUEUE is None:
        # first time this function is called
        # create logging queue and start log server
        __LOGGING_QUEUE = mp.Queue(-1)
        server = SharedLogListener(__LOGGING_QUEUE, _configure_root_logger)
        server.start()
    else:
        # the queue handler should be inherited by all child loggers
        logging.getLogger().addHandler(SharedLogHandler(__LOGGING_QUEUE))
