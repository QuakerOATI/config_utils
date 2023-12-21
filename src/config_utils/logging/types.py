import logging
from typing import Callable, Literal, Type, TypeAlias, Union

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


FilterType: TypeAlias = Union[
    Type[logging.Filter],
    Callable[[logging.LogRecord], Union[bool, logging.LogRecord]],
]


HandlerType: TypeAlias = Type[logging.Handler]
