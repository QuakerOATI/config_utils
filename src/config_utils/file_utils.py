import warnings
from contextlib import contextmanager
from inspect import isbuiltin, isclass, isfunction, ismodule
from pathlib import Path
from typing import Generator, Optional, Type, Union

_PROJECT_ROOT: Optional[Path] = Path(".")
__INIT_CALLED: bool = False


def init_project_root(path: str) -> None:
    global _PROJECT_ROOT, __INIT_CALLED
    if __INIT_CALLED:
        warnings.warn(f"Project root has already been set: {_PROJECT_ROOT}")
    else:
        _PROJECT_ROOT = Path(path)
        __INIT_CALLED = True


@contextmanager
def project_root(path: Union[str, Path] = _PROJECT_ROOT) -> Generator[Path, None, None]:
    """Temporarily set _PROJECT_ROOT global.

    Intended for use as a context manager.
    """
    global _PROJECT_ROOT
    old_project_root = _PROJECT_ROOT
    try:
        _PROJECT_ROOT = Path(path)
        yield _PROJECT_ROOT
    finally:
        _PROJECT_ROOT = old_project_root


def resolve_path(path: str) -> Path:
    global _PROJECT_ROOT
    path = Path(path)
    if not path.is_absolute():
        path = _PROJECT_ROOT / path
    return path.resolve()


def get_fully_qualified_name(obj: Type) -> str:
    """Get the fully-qualified name of an object."""
    if isclass(obj) or isfunction(obj):
        return f"{obj.__module__}.{obj.__qualname__}"
    elif ismodule(obj) or isbuiltin(obj):
        return obj.__name__
    else:
        name = ""
        if hasattr(obj, "__module__"):
            name += obj.__module__
        if hasattr(obj, "__qualname__"):
            name += f".{obj.__qualname__}"
        elif hasattr(obj, "__name__"):
            name += f".{obj.__name__}"
        return name
