import logging
from collections import OrderedDict
from dataclasses import dataclass
from typing import Iterable, Optional, Type, TypeAlias, Union

from . import LogLevel, _LoggingConfigurable
from .filters import FilterConfig, FilterType


@dataclass
class LoggerConfig(_LoggingConfigurable):
    level: LogLevel = logging.NOTSET
    propagate: Optional[bool] = None
    filters: Iterable[Union[FilterConfig, str]]


def DeclarativeLogger(
    level: LogLevel = logging.NOTSET,
    propagate: Optional[bool] = None,
    filters: Iterable[FilterType] = (),
    handlers: Iterable[HandlerType] = (),
) -> OrderedDict:
    """Get a configuration dict representing a logger config."""
    cfg = OrderedDict(level=level)
    if propagate is not None:
        cfg["propagate"] = propagate
    filters, handlers = list(filters), list(handlers)
    if filters:
        cfg["filters"] = filters
    if handlers:
        cfg["handlers"] = handlers
    return cfg


class AdaptedLogger(logging.Logger):
    """A logger that allows you to register adapters on a instance.

    Taken from this StackOverflow answer: https://stackoverflow.com/a/68287482
    """

    def __init__(self, name: str) -> None:
        """Create a new logger instance."""
        super().__init__(name)
        self._adapters = []

    def add_adapter(self, adapter: logging.LoggerAdapter, *args, **kwargs) -> None:
        """Preprocess this logger's input with the provided LoggerAdapter.

        Positional and keyword arguments after the first are passed to the
        adapter's constructor.
        """
        self._adapters.append(adapter(self, *args, **kwargs))

    def _log(self, level, msg, *args, **kwargs):
        """Let adapters modify the message and keyword arguments."""
        for adapter in self._adapters:
            msg, kwargs = adapter.process(msg, kwargs)
        return super()._log(level, msg, *args, **kwargs)
