from dataclasses import dataclass
from typing import Optional


@dataclass
class MongoConfig:
    host: str = "localhost"
    port: int = 27017
    database_name: str
    collection: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    authentication_db: Optional = None
