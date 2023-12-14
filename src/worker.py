import multiprocessing as mp
from abc import ABC, abstractmethod
from typing import Any, Callable, TypeVar

T = TypeVar("T")
R = TypeVar("R")


class QueueWorker:
    """A generic queue-based multiprocessing worker."""

    def __init__(
        self,
        process_message: Callable[[T], R],
        func: Callable[[R], Any],
        shared: mp.managers.SharedMemoryManager,
        proxy: mp.managers.SyncManager,
    ) -> None:
        """
        Args:
            process_message: callable to parse message and retrieve func args
            func: function to run ("work")
            shared: a multiprocessing.SharedMemoryManager, in case the
                computation needs to access shared objects
            proxy: a multiprocessing.SyncManager ("proxy factory"), used for
                dependency injection
        """
        self._process = process_message
        self._func = func
        self._shared = shared
        self._proxy = proxy

    @property
    def logger(self):
        return self._proxy.get_logger(__name__, self.__class__.__name__)

    def config(self, *keys):
        return self._proxy.get_config(*keys)

    def process_message(self, msg: T) -> R:
        return self._process(msg)

    def __call__(self, queue: mp.Queue):
        while True:
            msg = queue.get_nowait()  # don't block
            args = self.process_message(msg)
            yield self._func(*args)


class Model(ABC):
    """Base class for a forecasting model."""

    @abstractmethod
    def initialize(self) -> None:
        ...

    @abstractmethod
    def update(self) -> None:
        ...

    @abstractmethod
    def train(self) -> None:
        ...
