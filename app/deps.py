import secrets
from collections.abc import Iterator

from fastapi import Depends, Security
from fastapi.security import APIKeyHeader
from sqlalchemy.orm import Session

from app.config import settings
from app.db.session import get_db
from app.errors import UnauthorizedError
from app.repositories.sql import SqlStore

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False, description="Admin key for write operations")


def require_admin(api_key: str | None = Security(api_key_header)) -> None:
    if not api_key or not secrets.compare_digest(api_key, settings.admin_api_key):
        raise UnauthorizedError("Missing or invalid X-API-Key header")


def get_store(db: Session = Depends(get_db)) -> Iterator[SqlStore]:
    yield SqlStore(db)
