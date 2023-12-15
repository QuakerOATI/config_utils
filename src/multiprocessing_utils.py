import logging
import multiprocessing as mp
import sys
import threading
import time
import warnings
from multiprocessing.context import BaseContext
from multiprocessing.process import BaseProcess
from multiprocessing.queues import Queue
from multiprocessing.synchronize import Event
from typing import (Callable, Dict, Generic, Iterable, Optional, TypeVar,
                    TypeVarTuple)

MessageType = TypeVar("MessageType")
ResultType = TypeVar("ResultType")
ArgTypes = TypeVarTuple("ArgTypes")


def daemonize(
    ctx: BaseContext,
    worker: Callable[[*ArgTypes], ...],
    args: Iterable[*ArgTypes],
    initializer: Optional[Callable[[*ArgTypes], ...]] = None,
    name: Optional[str] = None,
) -> None:
    """Create a daemonized process in which to run a worker function.

    If an initializer function is provided, then the actual function executed
    in the worker process will consist of a call to the initializer followed
    by a call to the worker function.  Both functions will be called on the
    (unpacked) args provided.

    The constructed Process instance is returned.  It must be started by the
    caller.

    Args:
        ctx: multiprocessing context
        worker: function to daemonize
        args: iterable of arguments to pass to worker
        initializer: optional function to call before worker in subprocess
        name: name of the worker process

    Raises:
        ValueError: if initializer is not callable and is not None

    Returns:
        the daemonized worker process
    """

    if initializer is not None:
        if not callable(initializer):
            raise TypeError("Initializer must be callable")

        def wrapper(*args):
            initializer(*args)
            worker(*args)

        worker = wrapper

    process: BaseProcess = ctx.get_context().Process(
        target=worker, args=args, name=name
    )
    process.daemon = True
    return process


class QueueListener(Generic[MessageType, ResultType]):
    """Generic listener class for queue-based worker processes."""

    def __init__(
        self,
        queue: Queue,
        handler: Callable[[MessageType], ResultType],
        stop_event: Event = None,
        raise_on_exc: bool = True,
    ) -> None:
        """
        Args:
            queue: process-synchronized message queue
            handler: callable to run on each dequeued message
            stop_event: optional process-synchronized event to signal the
                listener to stop
            raise_on_exc: specifies whether the listener should swallow
                exceptions or reraise them (default)
        """
        self.queue = queue
        self.handler = handler
        self.stop_event = stop_event if stop_event is not None else Event()
        self.raise_on_exc = raise_on_exc

    def _should_stop(self) -> bool:
        return self.stop_event is None or self.stop_event.is_set()

    def listen(self):
        """Loop to dequeue messages and dispatch to handler threads."""
        while True:
            try:
                msg = self.queue.get()
            except OSError:
                # not sure if this is really necessary here
                # TODO: check this (cf. mp.managers.Server.accepter implementation)
                continue
            except Exception:
                if self.raise_on_exc:
                    raise
            t = threading.Thread(target=self.handler, args=(msg,))
            t.daemon = True
            t.start()

    def start(self):
        """Start the listener in a daemonized thread."""
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


class QueueListenerDaemon(Generic[MessageType, ResultType]):
    """Run a QueueListener in a daemonized process."""

    class QueueListenerDaemonWarning(Warning):
        pass

    @classmethod
    def _warn(cls, msg):
        warnings.warn(msg, cls.QueueListenerDaemonWarning)

    def _error(self, msg, exc_cls):
        if self.raise_on_exc:
            raise exc_cls(msg)
        else:
            self._warn(msg)

    def __init__(
        self,
        ctx: mp.context.BaseContext,
        queue: mp.queues.Queue,
        handler: Callable[[MessageType], ResultType],
        initializer: Callable[None, None],
        raise_on_exc: bool = True,
    ) -> None:
        """
        Args:
            ctx: multiprocessing context to use for creating processes and
                synchronization primitives
            queue: multiprocessing queue to process messages from
            initializer: configuration function to call in the listener
                subprocess before starting the listener
            raise_on_exc: whether to raise exceptions or issue warnings
        """
        self._stop_event = ctx.Event()
        self._listener = QueueListener(
            queue,
            handler,
            self._stop_event,
            raise_on_exc,
        )
        self._daemon = daemonize(self._listener.start, initializer=self.initializer)
        self.initializer = initializer
        self.raise_on_exc = raise_on_exc

    @property
    def pid(self) -> int:
        return self._daemon.pid

    def start_listener(self) -> None:
        """Start listener daemon."""
        if self._daemon.is_alive():
            self._error(
                "Listener was already running when start_listener was called",
                ValueError,
            )
        else:
            self._daemon.start()

    def _stop_daemon(self):
        delay = 0.1  # amount of time to wait between SIGTERM and SIGKILL
        try:
            self._daemon.terminate()
            time.sleep(delay)  # to allow process to handle SIGTERM
            if self._daemon.is_alive():
                self._warn(
                    f"Listener was not stopped {delay:2.1f}s after receiving SIGTERM.  Sending SIGKILL"
                )
                self._daemon.kill()
        finally:
            self._daemon.close()

    def stop_listener(self, timeout: float = -1) -> None:
        """Gracefully stop the listener daemon.

        The optional timeout parameter specifies how long to wait for the
        process to terminate before sending it a SIGTERM, followed by a
        SIGKILL if necessary.  Passing timeout=0 sends SIGTERM immediately.
        Negative timeouts are interpreted as infinite, i.e., the listener
        will never be forcibly killed.
        """
        if not self._daemon.is_alive():
            self._error("Daemon is not running", ValueError)

        # first, set the stop event to allow the worker to finish whatever it's doing
        self._stop_event.set()

        # kill the daemon if no timeout period
        if timeout == 0:
            self._stop_daemon()

        elif timeout > 0:
            time.sleep(timeout)
            self._stop_daemon()

    def refresh_daemon(self, timeout: float = -1):
        """Stop and replace the current listener daemon.

        The timeout parameter is passed to self.stop_listener().  If positive,
        it determines how long to wait for the listener process to stop
        gracefully before sending it a SIGTERM or SIGKILL.

        A subsequent call to self.start_listener() is required to start the
        refreshed daemon.
        """
        self.stop_listener(timeout)
        self._daemon = daemonize(self._listener.start, initializer=self.initializer)
