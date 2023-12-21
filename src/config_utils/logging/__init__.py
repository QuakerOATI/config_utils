import json
import logging
import multiprocessing as mp
from collections import OrderedDict
from contextlib import ContextDecorator
from dataclasses import asdict, dataclass, field, is_dataclass
from typing import (Any, Callable, Dict, Literal, Mapping, Optional, TypeAlias,
                    Union)

from dataclasses_json import DataClassJsonMixin, config, dataclass_json

from ..file_utils import get_fully_qualified_name

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


def get_loglevel(level: Union[str, int]) -> LogLevel:
    """Convenience function to get loglevel name.

    Exceptions raised by the logging module's lookup methods are caught, so
    barring exceptions raised by the level parameter itself, this function
    should never raise.

    Args:
        level: name of loglevel or numerical value
    """
    try:
        if isinstance(level, str):
            level = logging._checkLevel(level.upper())
        return logging._levelToName[level]
    except (ValueError, KeyError):
        return "NOTSET"


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


@dataclass_json
@dataclass
class SharedLogMessage:
    record: logging.LogRecord
    config: OrderedDict


@dataclass
class CustomLoggingObject(DataClassJsonMixin):
    func: Callable = field(
        metadata=config(
            field_name="()",
            encoder=get_fully_qualified_name,
            decoder=logging.config._resolve,
        )
    )
    args: Optional[Mapping[str, Any]] = None

    def to_dict(self, encode_json=False) -> Dict:
        """Unpack self.args into returned dict."""
        d = super().to_dict(encode_json)
        args = d.pop("args")
        return {**d, **args}


def _get_custom_dict_config(custom: Callable, **kwargs: Dict) -> OrderedDict:
    """Get a description of a custom object for use with logging.config."""
    return OrderedDict({"()": get_fully_qualified_name(custom), **kwargs})


class _DictConfigMixin:
    """Mixin to allow dynamic logging.config.dictConfig generation.

    To allow cooperative multi-inheritance, this class's constructor forwards
    its arguments to super().__init__().  Hence, this class (along with other
    mixins that follow the same pattern) should be inherited **before** any
    non-cooperative base classes.  For example:

    >>> # Foo inherits from _DictConfig first, so SomeBaseClass doesn't need
    >>> # to do anything to ensure that Foo gets all of _DictConfig's attrs
    >>> class Foo(_DictConfigMixin, SomeBaseClass)
    ...     pass
    """

    def __init__(self, *args, **kwargs) -> None:
        """Call parent constructor (cooperative multi-inheritance)"""
        super().__init__(*args, **kwargs)

    @classmethod
    def get_config(cls, **kwargs: Dict) -> OrderedDict:
        return _get_custom_dict_config(cls, **kwargs)
