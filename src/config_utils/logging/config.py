import logging
import sys
from dataclasses import Field, dataclass, field, fields
from functools import partial, singledispatchmethod, wraps
from itertools import islice
from logging import config as logging_config
from operator import or_, setitem, truth
from textwrap import shorten
from typing import (Any, Callable, Dict, Generic, Iterable, Iterator, Mapping,
                    Optional, Protocol, TypeVar)

from dataclasses_json import DataClassJsonMixin, config, dataclass_json

from ..file_utils import get_fully_qualified_name
from .types import DataclassType, FilterType, HandlerType, LogLevel
from .utils import get_loglevel


@wraps(field)
def _reference_field(*args, reference_name: str = None, **kwargs) -> Field:
    if reference_name is not None:
        kwargs.setdefault("metadata", {})["reference_name"] = reference_name
    return field(*args, **kwargs)


_callable = partial(
    _reference_field,
    metadata=config(
        field_name="()",
        encoder=get_fully_qualified_name,
        decoder=logging_config._resolve,
    ),
)

_log_level = partial(
    _reference_field,
    metadata=config(encoder=get_loglevel),
    default=logging.NOTSET,
)

_dict_default = partial(_reference_field, default_factory=dict)


class LoggingConfig(DataClassJsonMixin):
    """Mixin to encapsulate serialization of logging config objects."""

    _context: Dict[str, Any] = field(init=False)

    def __post_init__(self) -> None:
        self._context = Context()
        for f in fields(self):
            val = getattr(self, f.name)
            if isinstance(val, self.__class__):
                self._context += val._context
            if "udpate_context" in f.metadata:
                updater = f.metadata["udpate_context"]
                updater(self._context, val)

    def to_dict(
        self, encode_json=False, context: Optional[Dict[str, "LoggingConfig"]] = None
    ) -> Dict:
        """dict factory to ensure logging fields are correctly handled."""
        d = super().to_dict(encode_json)
        # args = d.pop("args", {})
        # return {**d, **args}
        for f in fields(self):
            spec = f.metadata.get("logging_config", {})


@dataclass
class FormatterConfig(LoggingConfig):
    format: str
    datefmt: Optional[str]


@dataclass
class FilterConfig(LoggingConfig):
    func: FilterType = _callable()
    args: Dict[str, Any] = _dict_default()


@dataclass
class HandlerConfig(LoggingConfig):
    handler: HandlerType = _callable()
    level: LogLevel = _log_level()
    formatter: Optional[FormatterConfig] = ...
    filters: Iterable[FilterConfig] = ()
    args: Dict[str, Any] = _dict_default()

    def _update_context(self, context: "LoggingConfigContext") -> None:
        if self.formatter is not None:
            context.formatters[id(self.formatter)] = self.formatter
        for filter in self.filters:
            context.filters[id(filter)] = filter


@dataclass
class LoggerConfig(LoggingConfig):
    name: str
    level: LogLevel = logging.NOTSET
    propagate: Optional[bool] = None
    filters: Iterable[FilterConfig] = ()
    handlers: Iterable[HandlerConfig] = ()


@dataclass
class LoggingConfigContext(LoggingConfig):
    formatters: Dict[str, FormatterConfig] = _dict_default()
    filters: Dict[str, FilterConfig] = _dict_default()
    handlers: Dict[str, HandlerConfig] = _dict_default()
    loggers: Dict[str, LoggerConfig] = _dict_default()
    version: int = 1
    root: Optional[LoggerConfig] = None
    incremental: bool = False
    disable_existing_loggers: bool = False


@dataclass_json
@dataclass
class SetLogLevel:
    name: str
    level: LogLevel = _log_level()


@dataclass_json
@dataclass
class SharedLogMessage:
    record: logging.LogRecord
    setup: LoggerConfig
    set_level: SetLogLevel
