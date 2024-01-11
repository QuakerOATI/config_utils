"""
Module to maintain a global configuration state.

The public API consists of the single function ``get_config``, which returns a
configuration dict wrapped in a ``ConfigProxy``.
"""

from __future__ import annotations

import json
import logging
import os
from functools import update_wrapper, wraps
from pathlib import Path
from typing import (
    Any,
    Final,
    Generic,
    Optional,
    overload,
    ParamSpec,
    Self,
    Type,
    TypeVar,
    Union,
)

_logger = logging.getLogger(__name__)
_config: Optional[dict] = None


class ConfigurationError(Exception):
    pass


T = TypeVar("T")
ReturnType = TypeVar("ReturnType")
Params = ParamSpec("Params")


class ProxyDescriptor(Generic[T]):
    """Descriptor for an attribute of an object wrapped in a Proxy."""

    def __init__(self, name: str = None, recurse: bool = False) -> None:
        """
        Args:
            name (optional): specify the name of the instance attribute to
                retrieve.  If None, then name is set in self.__set_name__.
            recurse (optional): whether to ensure that the retrieved
                attribute is wrapped in an instance of the owner's Proxy
                class if it belongs to the Proxy's wrapped class.
        """
        self.name = name
        self.recurse = recurse

    def __set_name__(self, owner: Type[Proxy[T]], name: str) -> None:
        if self.name is None:
            self.name = name

    @overload
    def __get__(self, obj: None, cls: None) -> ProxyDescriptor:
        ...

    @overload
    def __get__(self, obj: Proxy[T], cls: Type[Proxy[T]]) -> Any:
        ...

    def __get__(
        self,
        obj: Union[Proxy[T], None],
        cls: Union[Type[Proxy[T]], None],
    ) -> Any:
        # if called on a class, return the descriptor instance
        if obj is None:
            return self
        # if called on an instance, return the wrapped object's attribute
        attr = getattr(obj._instance, self.name)
        if self.recurse:
            return cls.ensure_proxy(attr)
        return attr


class Proxy(Generic[T]):
    """Manage access to attributes and methods of wrapped class."""

    READONLY: Final[bool] = True
    _wrapped_class: Final[Type[T]]

    def __init__(self, instance: T) -> None:
        if not isinstance(instance, self._wrapped_class):
            raise TypeError(
                f"Proxy type {self.__class__} can only wrap objects of type {self._wrapped_class}"
            )
        # bypass self.__setattr__ to support readonly behavior
        super().__setattr__("_instance", instance)

    def __repr__(self) -> str:
        return f"{self.__class__}({self._instance!r})"

    def __str__(self) -> str:
        return f"{self.__class__}({self._instance})"

    def __setattr__(self, name: str, value: object) -> None:
        if self.READONLY:
            raise TypeError(
                f"{self.__class__!r} object does not support attribute assignment"
            )
        else:
            return super().__setattr__(name, value)

    @classmethod
    def new(cls, *args, **kwargs) -> Self:
        """Create Proxy around a new instance of wrapped class.

        Parameters are passed as-is to the constructor of the wrapped class.
        """
        instance = cls._wrapped_class(*args, **kwargs)
        return cls(instance)

    @classmethod
    def ensure_proxy(cls, obj: object):
        """Ensure that cls._wrapped_class objects are wrapped with a proxy.

        In addition to wrapping objects, this function can also be used as a
        function decorator, in which case it will check the type of the
        function's return value and return a Proxy containing it if
        appropriate.

        Args:
            obj: object to check and wrap in a Proxy if appropriate.  Can be
                an "ordinary" object or a callable.

        TODO: Implement class decorator functionality
        """
        if isinstance(obj, cls):
            return obj
        elif isinstance(obj, cls._wrapped_class):
            return cls(obj)
        elif callable(obj):
            # BUG: This raises if obj is a class
            @wraps(obj)
            def wrapper(*args, **kwargs):
                result = obj(*args, **kwargs)
                return cls.ensure_proxy(result)

            return wrapper
        elif isinstance(obj, list):
            return [cls.ensure_proxy(elem) for elem in obj]
        elif isinstance(obj, tuple):
            return tuple(cls.ensure_proxy(elem) for elem in obj)
        return obj


class ConfigProxy(Proxy[dict]):
    """Readonly wrapper around a configuration dict.

    Supports attribute-style lookup of keys, e.g.:
    >>> c = ConfigProxy(a=1, b=2)
    >>> print(c.a)
    1
    """

    READONLY = True
    _wrapped_class = dict

    __getitem__ = ProxyDescriptor(recurse=True)
    get = ProxyDescriptor(recurse=True)
    keys = ProxyDescriptor(recurse=True)
    values = ProxyDescriptor(recurse=True)

    def __getattr__(self, name: str) -> object:
        try:
            return self.__getattribute__(name)
        except AttributeError:
            return self[name]

    @classmethod
    def _from_json(cls, json_file: Union[str, Path]) -> Self:
        try:
            with Path(json_file).open("r") as file:
                return cls(json.load(file))
        except (TypeError, json.JSONDecodeError) as e:
            raise ConfigurationError(
                f"Incorrect JSON object type or malformed JSON parsed from file: {json_file}"
            ) from e


def _get_configfile() -> Path:
    return Path(
        os.getenv(
            "WSF_CONFIG_FILE",
            Path(__file__).parent.parent.joinpath("configuration.json"),
        )
    )


def get_config(config_file: Optional[Union[str, Path]] = None) -> ConfigProxy:
    """Get a readonly ConfigProxy containing data from config file.

    If no parameter is provided, a proxy to the global configuration dict is
    returned; otherwise, the parameter is treated as the path of a JSON file to
    parse.

    Args:
        config_file (optional): path to JSON configuration file
    """
    if config_file is not None:
        return ConfigProxy._from_json(config_file)
    global _config
    if _config is None:
        conf_file = _get_configfile()
        try:
            with conf_file.open("r") as cfg:
                _config = json.load(cfg)
                _logger.info("Read configuration file %s", conf_file)
        except Exception as e:
            msg = "Failed to read configuration file %s"
            _logger.exception(msg, conf_file, exc_info=True)
            raise ConfigurationError(msg % conf_file) from e
    return ConfigProxy(_config)


class WSFConfigMixin:
    """Mixin for classes that require WSF configuration information."""

    def __init__(self, *args, **kwargs):
        return super().__init__(*args, **kwargs)

    @classmethod
    @property
    def config(self) -> ConfigProxy:
        return get_config()

    @classmethod
    @property
    def logger(self) -> logging.Logger:
        return logging.getLogger(self.__class__.__qualname__)


def configure_wsf(klass: Type[object]):
    """Class decorator for classes that require WSF configuration data."""
    return update_wrapper(
        type(klass.__name__, (klass, WSFConfigMixin), {}),
        klass,
        updated=(),
    )
