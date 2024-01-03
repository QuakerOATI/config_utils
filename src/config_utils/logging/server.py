import logging
import multiprocessing as mp
import warnings
from functools import partial
from logging import config as logging_config
from typing import Optional

from ..multiprocessing_utils import QueueListenerDaemon
from .config import LoggerConfig, SharedLogMessage

__LOGGER_QUEUE: Optional[mp.Queue] = None

_LOGGER_CONFIG_METADATA = {
    "version": 1,
    "disable_existing_loggers": False,
}


class SharedLoggerException(Exception):
    pass


def _handle_shared_log_message(msg: SharedLogMessage) -> None:
    """Apply the logging config in msg and handle the record.

    This should ONLY be called by loggers in the log listener's subprocess.
    It should never be necessary to call this function directly.
    """
    if msg.config is not None:
        try:
            dict_config = {
                **_LOGGER_CONFIG_METADATA,
                "loggers": {msg.config.name: msg.config.to_dict()},
            }
            logging_config.dictConfig(dict_config)
        except Exception:
            logging.getLogger(__name__).exception(
                "Could not apply logging config %s", msg.config, exc_info=True
            )
    if msg.record is not None:
        logging.getLogger(msg.record.name).handle(msg.record)


def get_shared_logger(name: str, config: LoggerConfig) -> logging.Logger:
    """Create a shared logger and setup the appropriate handlers.

    Configuration is done in two stages:
        - on the **server side**, i.e., in the listener server's subprocess
        - on the **client side**, i.e., in the calling process

    The provided configuration dict determines the configuration of the
    server-side logger, which is why it must be a dict rather than a callable
    (it has to be pickleable).

    The client logger is **always** configured with a single QueueHandler. Its
    only function is to place logging messages on the logger queue, to be
    processed by the server-side logger in its dedicated subprocess.

    If it is necessary to wrap the returned logger in a LoggerAdapter--e.g.,
    if custom keyword arguments will be passed to logger methods--then the
    caller should arrange for this by calling logging.setLoggerClass() prior
    to invoking this function, typically in a __main__.py or __init__.py.

    Args:
        name: name of logger (same as argument to logging.getLogger)
        config: dictionary to be passed to logging.config.dictConfig.  A
            default configuration can be specified using this module's
            setDefaultLoggingConfig() function.
        level: optional loglevel specification (defaults to logging.NOTSET)

    Returns:
        logger instance, configured with a single QueueHandler and set to the
        specified level

    Raises:
        SharedLoggerException: if called before init_server
    """
    global __LOGGER_QUEUE
    if __LOGGER_QUEUE is None:
        raise SharedLoggerException(
            "Shared logging server must be initialized before calling get_shared_logger"
        )
    msg = SharedLogMessage(config=config)
    __LOGGER_QUEUE.put(msg)


def init_server(ctx: mp.context.BaseContext) -> None:
    """Initialize and start log server process.

    This should only be called once.  A warning will be raised on any
    subsequent calls.
    """
    global __LOGGER_QUEUE
    if __LOGGER_QUEUE is not None:
        warnings.warn("Logging server has already been initialized")
        return
    __LOGGER_QUEUE = ctx.Queue(-1)

    # cache this before we fork to a new process
    logger_class = logging.getLoggerClass()

    daemon = QueueListenerDaemon(
        ctx,
        __LOGGER_QUEUE,
        _handle_shared_log_message,
        initializer=partial(logging.setLoggerClass, logger_class),
        raise_on_exc=True,
    )
    daemon.start_listener()
