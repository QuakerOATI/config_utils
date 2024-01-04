from abc import ABC, abstractmethod
from typing import Any, Optional, Self


class ContextMixin(ABC):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

    @abstractmethod
    def insert(self, item: Any, *args, **kwargs) -> None:
        ...

    @abstractmethod
    def merge(self, other: Self, *args, **kwargs) -> None:
        ...

    def join(self, obj: Any, *args, **kwargs) -> None:
        if isinstance(obj, self.__class__):
            self.merge(obj, *args, **kwargs)
        else:
            self.insert(obj, *args, **kwargs)


class ListContext(list, ContextMixin):
    def insert(self, item: Any) -> None:
        self.append(item)

    def merge(self, other: Self) -> None:
        self.extend(other)


class DictContext(dict, ContextMixin):
    def _get_identifier(self, item: Any, key: Optional[str]) -> str | int:
        if key is not None:
            return str(key)
        elif hasattr(item, "name"):
            return item.name
        elif hasattr(item, "__name__"):
            return item.__name__
        else:
            return id(item)

    def _insert_item(self, key, value):
        if key in self and isinstance(self[key], ContextMixin):
            self[key].join(value)
        else:
            self[key] = value

    def insert(self, item: Any, key: Optional[str] = None) -> None:
        self._insert_item(self._get_identifier(item, key), item)

    def merge(self, other: Self) -> None:
        for k, v in other.items():
            self._insert_item(k, v)
