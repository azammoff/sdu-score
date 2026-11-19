"""PostgreSQL storage (Assignment 6): the same Store/Table interface, backed by a SQLAlchemy session."""

from typing import Any, Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import models

T = TypeVar("T", bound=models.Base)


class SqlTable(Generic[T]):
    def __init__(self, session: Session, model: type[T]):
        self.session = session
        self.model = model

    def add(self, **fields: Any) -> T:
        obj = self.model(**fields)
        self.session.add(obj)
        self.session.flush()  # assigns the id and surfaces constraint errors early
        return obj

    def get(self, id: int) -> T | None:
        return self.session.get(self.model, id)

    def all(self) -> list[T]:
        return list(self.session.scalars(select(self.model).order_by(self.model.id)))

    def where(self, **equals: Any) -> list[T]:
        return list(self.session.scalars(select(self.model).filter_by(**equals).order_by(self.model.id)))

    def update(self, obj: T, **fields: Any) -> T:
        for key, value in fields.items():
            setattr(obj, key, value)
        self.session.flush()
        return obj

    def delete(self, obj: T) -> None:
        self.session.delete(obj)
        self.session.flush()


class SqlStore:
    def __init__(self, session: Session):
        self.session = session
        self.faculties = SqlTable(session, models.Faculty)
        self.teams = SqlTable(session, models.Team)
        self.players = SqlTable(session, models.Player)
        self.tournaments = SqlTable(session, models.Tournament)
        self.enrollments = SqlTable(session, models.Enrollment)
        self.matches = SqlTable(session, models.Match)
        self.events = SqlTable(session, models.MatchEvent)

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()
