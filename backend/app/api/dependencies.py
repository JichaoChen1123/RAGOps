from collections.abc import Iterator

from fastapi import Request
from sqlalchemy.orm import Session

from app.persistence.db import Database


def get_database(request: Request) -> Database:
    return request.app.state.database


def get_session(request: Request) -> Iterator[Session]:
    database: Database = request.app.state.database
    with database.session() as session:
        yield session
