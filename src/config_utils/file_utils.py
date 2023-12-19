import warnings
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

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
def project_root(path: str) -> None:
    """Temporarily set _PROJECT_ROOT global.

    Intended for use as a context manager.
    """
    global _PROJECT_ROOT
    old_project_root = _PROJECT_ROOT
    try:
        _PROJECT_ROOT = Path(path)
        yield
    finally:
        _PROJECT_ROOT = old_project_root


def resolve_path(path: str) -> Path:
    global _PROJECT_ROOT
    path = Path(path)
    if not path.is_absolute():
        path = _PROJECT_ROOT / path
    return path.resolve()
