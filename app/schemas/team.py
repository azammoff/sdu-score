from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from app.schemas.common import ORMModel
from app.schemas.faculty import FacultyRead
from app.schemas.player import PlayerRead

TeamName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=60)]
CoachName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=60)]


class TeamCreate(BaseModel):
    name: TeamName = Field(examples=["ENS Eagles"])
    faculty_id: int | None = Field(default=None, gt=0, examples=[1])
    coach_name: CoachName | None = Field(default=None, examples=["Bekzat Ospanov"])


class TeamUpdate(BaseModel):
    name: TeamName | None = None
    faculty_id: int | None = Field(default=None, gt=0)
    coach_name: CoachName | None = None


class TeamRead(ORMModel):
    id: int
    name: str
    faculty_id: int | None
    coach_name: str | None


class TeamDetail(TeamRead):
    faculty: FacultyRead | None
    players: list[PlayerRead]
    tournament_ids: list[int]


class TeamStats(BaseModel):
    team_id: int
    team_name: str
    tournament_id: int | None
    played: int
    wins: int
    draws: int
    losses: int
    goals_for: int
    goals_against: int
    goal_difference: int
    points: int
    clean_sheets: int
    yellow_cards: int
    red_cards: int
