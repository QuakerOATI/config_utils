import logging
import multiprocessing as mp

from . import SharedLogMessage

__LOG_MESSAGES = None


def handle_shared_log_message(msg: SharedLogMessage) -> None:
    """Apply the logging config in msg and handle the record."""
    if msg.config is not None:
        logging.config.dictConfig(msg.config)
    if msg.record is not None:
        logging.getLogger(msg.record.name).handle(msg.record)


def init_server(ctx: mp.context.BaseContext) -> None:
    """Initialize and start log server process.

    This should only be called once.  A warning will be raised on any
    subsequent calls.
    """
    ...
