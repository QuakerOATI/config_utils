import argparse
import configparser
import json
import logging
import multiprocessing as mp
import sys
from functools import wraps
from typing import (Any, Callable, Dict, Iterable, List, Optional, ParamSpec,
                    Tuple)

import yaml

from .logging import setup_logging

Params = ParamSpec("Params")


class SharedLogger(mp.managers.SyncManager):
    def __init__(
        self,
        handler_factory: Callable[[str], Iterable[logging.Handler]],
        address=None,
        authkey=None,
        serializer="pickle",
        ctx: mp.context.BaseContext = None,
        *,
        shutdown_timeout: float = 1.0,
    ) -> None:
        super().__init__(
            address, authkey, serializer, ctx, shutdown_timeout=shutdown_timeout
        )
        self._logging_queue = self.Queue(-1)
        self._handler_factory = handler_factory
        self._loggers = self.dict()

    def _configure_logger(self, name: str) -> None:
        ...

    def initializer(
        self, init: Optional[Callable[Params, Any]]
    ) -> Callable[Params, Any]:
        """Decorator to ensure the shared logger is properly initialized."""

        @wraps(init)
        def wrapper(*args, **kwargs) -> Any:
            logger = self.logging.getLogger()
            logger.addHandler(
                self.logging.handlers.QueueListener(self._queue, *self._handlers)
            )
            if init is not None:
                init(*args, **kwargs)

        return wrapper

    def start(
        self,
        initializer: Optional[Callable[..., Any]],
        initargs: Iterable[Any],
    ) -> None:
        super().start(self.initializer(initializer), initargs)

    def getLogger(self, name: str) -> logging.Logger:
        logger = self.logging.getLogger(name)
        logger.addHandler(self.logging.handlers.QueueHandler(self._queue))
        return logger

    @classmethod
    def add_shared_log_handlers(cls, logger: logging.Logger) -> None:
        for _, queue in cls._log_handler_queues.items():
            logger.addHandler(logger.handlers.QueueHandler(queue))


def parse_options(args: List[str]) -> None:
    ...


def setup_forkserver() -> mp.context.ForkServerContext:
    ctx = mp.get_context(method="forkserver")
    ctx.set_forkserver_preload("configuration")
    return ctx


def get_managers(
    ctx: mp.context.BaseContext,
) -> Tuple[mp.managers.BaseManager, mp.managers.SharedMemoryManager]:
    # use to create "stateful proxies," e.g., loggers
    resource_manager = SharedLogger(ctx=ctx.get_context())

    # use for large objects that can be dumped to bytes easily
    # e.g. numpy arrays, pandas dataframes
    memory_manager = mp.managers.SharedMemoryManager(ctx=ctx.get_context())

    return resource_manager, memory_manager


if __name__ == "__main__":
    options = parse_options(sys.argv[1:])

    mp_ctx = setup_forkserver()
    resources, shared_memory = get_managers()

    setup_logging(manager=resources)
    pool = mp.pool.Pool(initializer=setup_logging, initargs=(resources))
