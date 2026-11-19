"""Storage interface used by the service layer.

Services only talk to a ``Store`` made of ``Table`` objects. Stage 1 (Assignment 5)
implemented it in memory; Assignment 6 swaps in a SQLAlchemy implementation (sql.py)
without touching services, schemas or routers.
"""

from typing import Any, Protocol, TypeVar

T = TypeVar("T")


class Table(Protocol[T]):
    def add(self, **fields: Any) -> T: ...
    def get(self, id: int) -> T | None: ...
    def all(self) -> list[T]: ...
    def where(self, **equals: Any) -> list[T]: ...
    def update(self, obj: T, **fields: Any) -> T: ...
    def delete(self, obj: T) -> None: ...


class Store(Protocol):
    session: Any  # the SQLAlchemy session, used for queries that need joins or aggregates

    faculties: Table
    teams: Table
    players: Table
    tournaments: Table
    enrollments: Table
    matches: Table
    events: Table

    def commit(self) -> None: ...
    def rollback(self) -> None: ...
