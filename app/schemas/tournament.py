from datetime import date
from typing import Annotated, Self

from pydantic import BaseModel, Field, StringConstraints, model_validator

from app.enums import TournamentStatus
from app.schemas.common import ORMModel

TournamentName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=100)]
Season = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^\d{4}(/\d{4})?$")]
MaxTeams = Annotated[int, Field(ge=2, le=64)]


class TournamentCreate(BaseModel):
    name: TournamentName = Field(examples=["SDU Autumn Cup"])
    season: Season = Field(examples=["2026/2027"], description="e.g. 2026 or 2026/2027")
    start_date: date = Field(examples=["2026-11-01"])
    end_date: date = Field(examples=["2026-12-20"])
    max_teams: MaxTeams = Field(default=8, examples=[8])

    @model_validator(mode="after")
    def check_dates(self) -> Self:
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self


class TournamentUpdate(BaseModel):
    name: TournamentName | None = None
    season: Season | None = None
    start_date: date | None = None
    end_date: date | None = None
    max_teams: MaxTeams | None = None


class TournamentRead(ORMModel):
    id: int
    name: str
    season: str
    start_date: date
    end_date: date
    max_teams: int
    status: TournamentStatus


class TournamentDetail(TournamentRead):
    team_count: int
    match_count: int
    finished_match_count: int
    stages: list[str]
    groups: list[str]


class EnrollmentCreate(BaseModel):
    team_id: int = Field(gt=0, examples=[1])


class StandingRow(BaseModel):
    position: int
    team_id: int
    team_name: str
    played: int
    wins: int
    draws: int
    losses: int
    goals_for: int
    goals_against: int
    goal_difference: int
    points: int


class TopScorerRow(BaseModel):
    rank: int
    player_id: int
    player_name: str
    team_id: int
    team_name: str
    goals: int
    assists: int
