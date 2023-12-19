import multiprocessing as mp
from dataclasses import dataclass
from multiprocessing import managers
from pathlib import Path
from typing import Dict, Optional, TypeAlias, Union

ConfigObject: TypeAlias = Union[Dict, str]


@dataclass
class MongoConfig:
    database_name: str
    host: str = "localhost"
    port: int = 27017
    collection: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    authentication_db: Optional = None


class Configuration(managers.BaseManager):
    """Manage a shared config object in a MP setting."""

    def parse_cli_args(self, args) -> None:
        ...

    def load_json(self, file: Union[Path, str]):
        ...

    def load_yaml(self, file: Union[Path, str]):
        ...
