from datetime import datetime
from typing import Annotated, Self

from pydantic import BaseModel, Field, StringConstraints, field_validator, model_validator

from app.enums import EventType, MatchStatus
from app.schemas.common import ORMModel, to_naive_utc

Venue = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=100)]
Stage = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]
GroupName = Annotated[str, StringConstraints(strip_whitespace=True, to_upper=True, pattern=r"^[A-Za-z0-9]{1,10}$")]


class MatchCreate(BaseModel):
    home_team_id: int = Field(gt=0, examples=[1])
    away_team_id: int = Field(gt=0, examples=[2])
    kickoff: datetime = Field(examples=["2026-11-25T15:00:00"])
    venue: Venue = Field(default="SDU Main Stadium", examples=["SDU Main Stadium"])
    stage: Stage | None = Field(default=None, examples=["Tour 1"], description="Round or stage, e.g. Tour 3, Quarter-final")
    group_name: GroupName | None = Field(default=None, examples=["A"])
    leg: int | None = Field(default=None, ge=1, le=2, description="1 or 2 for two-legged ties")

    _normalize_kickoff = field_validator("kickoff")(to_naive_utc)

    @model_validator(mode="after")
    def check_teams(self) -> Self:
        if self.home_team_id == self.away_team_id:
            raise ValueError("A team cannot play against itself")
        return self


class MatchUpdate(BaseModel):
    kickoff: datetime | None = None
    venue: Venue | None = None
    stage: Stage | None = None
    group_name: GroupName | None = None

    @field_validator("kickoff")
    @classmethod
    def normalize(cls, value: datetime | None) -> datetime | None:
        return to_naive_utc(value) if value else value


class MatchRead(ORMModel):
    id: int
    tournament_id: int
    home_team_id: int
    home_team_name: str
    away_team_id: int
    away_team_name: str
    kickoff: datetime
    venue: str
    status: MatchStatus
    home_score: int
    away_score: int
    home_penalties: int | None
    away_penalties: int | None
    stage: str | None
    group_name: str | None
    leg: int | None


class EventCreate(BaseModel):
    type: EventType = Field(examples=[EventType.GOAL])
    minute: int = Field(ge=1, le=130, examples=[23], description="1-130 (extra time included)")
    player_id: int = Field(gt=0, examples=[1])
    assist_player_id: int | None = Field(default=None, gt=0, description="Only for goals")

    @model_validator(mode="after")
    def check_assist(self) -> Self:
        if self.assist_player_id is not None:
            if self.type != EventType.GOAL:
                raise ValueError("assist_player_id is only allowed for goals")
            if self.assist_player_id == self.player_id:
                raise ValueError("A player cannot assist their own goal")
        return self


class EventRead(ORMModel):
    id: int
    match_id: int
    type: EventType
    minute: int | None
    player_id: int
    player_name: str
    team_id: int
    assist_player_id: int | None
    assist_player_name: str | None
    is_auto: bool


class Score(BaseModel):
    home: int
    away: int


class EventCreateResult(BaseModel):
    event: EventRead
    auto_events: list[EventRead] = Field(description="Events added automatically, e.g. red card after a second yellow")
    score: Score


class TeamBrief(ORMModel):
    id: int
    name: str


class MatchDetail(MatchRead):
    home_team: TeamBrief
    away_team: TeamBrief
    events: list[EventRead]
