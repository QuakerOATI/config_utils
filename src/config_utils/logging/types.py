import logging
from pathlib import Path
from typing import (Callable, Dict, Literal, Mapping, Optional, Protocol, Type,
                    TypeAlias, Union)

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

PathLike: TypeAlias = Union[Path, str]


HandlerType: TypeAlias = Type[logging.Handler]


class DataclassType(Protocol):
    __dataclass_fields__: Dict
    __dataclass_params__: Dict
    __post_init__: Optional[Callable]
