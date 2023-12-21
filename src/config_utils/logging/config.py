import logging
from dataclasses import dataclass, field
from functools import partial
from logging import config as logging_config
from operator import getitem
from typing import Any, Callable, Dict, Iterable, Optional

from dataclasses_json import DataClassJsonMixin, config, dataclass_json

from ..file_utils import get_fully_qualified_name
from .types import FilterType, HandlerType, LogLevel


def callable_field(
    default: Optional[Any] = None,
    default_factory: Optional[Callable[[], Any]] = None,
    init=True,
    repr=True,
    hash=True,
    compare=True,
):
    """Factory function for dataclass fields JSON-encoded to "()".

    This is a convenience function to support the syntax of the logging
    package's dictConfig mechanism.
    """
    return field(
        metadata=config(
            field_name="()",
            encoder=get_fully_qualified_name,
            decoder=logging_config._resolve,
        ),
        default=default,
        init=init,
        repr=repr,
        hash=hash,
        compare=compare,
    )


@dataclass
class CustomLoggingObjectMixin(DataClassJsonMixin):
    """Unpack custom logging configs' args on serialization"""

    def to_dict(self, encode_json=False) -> Dict:
        """Unpack self.args into returned dict."""
        d = super().to_dict(encode_json)
        args = d.pop("args", {})
        return {**d, **args}


@dataclass
class FormatterConfig(CustomLoggingObjectMixin):
    format: str
    datefmt: Optional[str]


@dataclass
class FilterConfig(CustomLoggingObjectMixin):
    func: FilterType = callable_field()
    args: Dict[str, Any] = field(default_factory=dict)


@dataclass
class HandlerConfig(CustomLoggingObjectMixin):
    handler: HandlerType = callable_field()
    level: LogLevel = field(
        metadata=config(encoder=partial(getitem, logging._levelToName)),
        default=logging.NOTSET,
    )
    formatter: Optional[FormatterConfig] = None
    filters: Iterable[FilterConfig] = ()
    args: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LoggerConfig(CustomLoggingObjectMixin):
    name: str
    level: LogLevel = logging.NOTSET
    propagate: Optional[bool] = None
    filters: Iterable[FilterConfig] = ()
    handlers: Iterable[HandlerConfig] = ()
    formatters: Iterable[FormatterConfig] = field(init=False)

    def to_dict(
        self,
        encode_json=False,
        disable_existing_loggers: bool = False,
        version: int = 1,
    ) -> dict:
        ret = {
            "version": version,
            "disable_existing_loggers": disable_existing_loggers,
        }
        handlers = {}
        formatters = {}
        for i, h in enumerate(self.handlers):
            ret.setdefault("handlers", {})[str(i)] = h.to_dict()
            handlers.append(str(i))
            if h.formatter is not None:
                formatters[str(len(formatters))] = h.formatter.to_dict()
        d = super().to_dict(encode_json)
        del d["name"]
        d["handlers"] = ...
        return ret


@dataclass_json
@dataclass
class SharedLogMessage:
    record: logging.LogRecord
    config: LoggerConfig
