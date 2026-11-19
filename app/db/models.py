"""Database tables for SDU Score.

Faculty 1──* Team 1──* Player
Tournament *──* Team  through Enrollment
Tournament 1──* Match, Team 1──* Match (as home and as away team)
Match 1──* MatchEvent, Player 1──* MatchEvent
"""

from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.enums import EventType, MatchStatus, Position, TournamentStatus


def pg_enum(enum_cls: type[StrEnum], name: str) -> Enum:
    """Store the enum *values* ("goal", "GK", ...) rather than Python member names."""
    return Enum(enum_cls, name=name, values_callable=lambda e: [m.value for m in e], validate_strings=True)


class Faculty(Base):
    __tablename__ = "faculties"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    code: Mapped[str] = mapped_column(String(10), unique=True)

    teams: Mapped[list["Team"]] = relationship(back_populates="faculty")


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(60), unique=True)
    faculty_id: Mapped[int | None] = mapped_column(ForeignKey("faculties.id", ondelete="RESTRICT"), index=True)
    coach_name: Mapped[str | None] = mapped_column(String(60))

    faculty: Mapped[Faculty | None] = relationship(back_populates="teams")
    players: Mapped[list["Player"]] = relationship(
        back_populates="team", cascade="all, delete-orphan", passive_deletes=True, order_by="Player.jersey_number"
    )
    enrollments: Mapped[list["Enrollment"]] = relationship(
        back_populates="team", cascade="all, delete-orphan", passive_deletes=True
    )


class Player(Base):
    __tablename__ = "players"
    __table_args__ = (
        UniqueConstraint("team_id", "jersey_number", name="uq_players_team_jersey"),
        CheckConstraint("jersey_number BETWEEN 1 AND 99", name="jersey_range"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), index=True)
    first_name: Mapped[str] = mapped_column(String(50))
    last_name: Mapped[str] = mapped_column(String(50))
    student_id: Mapped[str | None] = mapped_column(String(9), unique=True)
    jersey_number: Mapped[int | None] = mapped_column(Integer)
    position: Mapped[Position | None] = mapped_column(pg_enum(Position, "player_position"))

    team: Mapped[Team] = relationship(back_populates="players")

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


class Tournament(Base):
    __tablename__ = "tournaments"
    __table_args__ = (
        UniqueConstraint("name", "season", name="uq_tournaments_name_season"),
        CheckConstraint("end_date >= start_date", name="dates_order"),
        CheckConstraint("max_teams BETWEEN 2 AND 64", name="max_teams_range"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    season: Mapped[str] = mapped_column(String(9))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    max_teams: Mapped[int] = mapped_column(Integer, default=8)
    status: Mapped[TournamentStatus] = mapped_column(
        pg_enum(TournamentStatus, "tournament_status"), default=TournamentStatus.UPCOMING, index=True
    )

    enrollments: Mapped[list["Enrollment"]] = relationship(
        back_populates="tournament", cascade="all, delete-orphan", passive_deletes=True
    )
    matches: Mapped[list["Match"]] = relationship(
        back_populates="tournament", cascade="all, delete-orphan", passive_deletes=True, order_by="Match.kickoff"
    )


class Enrollment(Base):
    __tablename__ = "enrollments"
    __table_args__ = (UniqueConstraint("tournament_id", "team_id", name="uq_enrollments_tournament_team"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tournament_id: Mapped[int] = mapped_column(ForeignKey("tournaments.id", ondelete="CASCADE"), index=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), index=True)
    enrolled_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    tournament: Mapped[Tournament] = relationship(back_populates="enrollments")
    team: Mapped[Team] = relationship(back_populates="enrollments")


class Match(Base):
    __tablename__ = "matches"
    __table_args__ = (
        CheckConstraint("home_team_id <> away_team_id", name="different_teams"),
        CheckConstraint("home_score >= 0 AND away_score >= 0", name="scores_non_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tournament_id: Mapped[int] = mapped_column(ForeignKey("tournaments.id", ondelete="CASCADE"), index=True)
    home_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="RESTRICT"), index=True)
    away_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="RESTRICT"), index=True)
    kickoff: Mapped[datetime] = mapped_column(DateTime, index=True)
    venue: Mapped[str] = mapped_column(String(100))
    status: Mapped[MatchStatus] = mapped_column(
        pg_enum(MatchStatus, "match_status"), default=MatchStatus.SCHEDULED, index=True
    )
    home_score: Mapped[int] = mapped_column(Integer, default=0)
    away_score: Mapped[int] = mapped_column(Integer, default=0)
    stage: Mapped[str | None] = mapped_column(String(40))  # "Tour 3", "Quarter-final", "Final", ...
    group_name: Mapped[str | None] = mapped_column(String(10))  # "A", "B", ... for group stages
    leg: Mapped[int | None] = mapped_column(Integer)  # 1 or 2 for two-legged ties
    home_penalties: Mapped[int | None] = mapped_column(Integer)
    away_penalties: Mapped[int | None] = mapped_column(Integer)
    source_post_id: Mapped[int | None] = mapped_column(Integer, index=True)  # Telegram post it was imported from

    tournament: Mapped[Tournament] = relationship(back_populates="matches")
    home_team: Mapped[Team] = relationship(foreign_keys=[home_team_id])
    away_team: Mapped[Team] = relationship(foreign_keys=[away_team_id])

    @property
    def home_team_name(self) -> str:
        return self.home_team.name

    @property
    def away_team_name(self) -> str:
        return self.away_team.name
    events: Mapped[list["MatchEvent"]] = relationship(
        back_populates="match",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="(MatchEvent.minute, MatchEvent.id)",
    )


class MatchEvent(Base):
    __tablename__ = "match_events"
    __table_args__ = (CheckConstraint("minute BETWEEN 1 AND 130", name="minute_range"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"), index=True)
    type: Mapped[EventType] = mapped_column(pg_enum(EventType, "event_type"))
    minute: Mapped[int | None] = mapped_column(Integer)  # unknown for some imported events
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="RESTRICT"), index=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="RESTRICT"), index=True)
    assist_player_id: Mapped[int | None] = mapped_column(ForeignKey("players.id", ondelete="RESTRICT"))
    is_auto: Mapped[bool] = mapped_column(Boolean, default=False)

    match: Mapped[Match] = relationship(back_populates="events")
    player: Mapped[Player] = relationship(foreign_keys=[player_id])
    assist_player: Mapped[Player | None] = relationship(foreign_keys=[assist_player_id])

    @property
    def player_name(self) -> str:
        return self.player.full_name

    @property
    def assist_player_name(self) -> str | None:
        return self.assist_player.full_name if self.assist_player else None
