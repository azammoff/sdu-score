from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from app.enums import Position
from app.schemas.common import ORMModel

PersonName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
StudentId = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^\d{9}$")]
Jersey = Annotated[int, Field(ge=1, le=99)]


class PlayerCreate(BaseModel):
    first_name: PersonName = Field(examples=["Aidar"])
    last_name: PersonName = Field(examples=["Nurlanov"])
    student_id: StudentId | None = Field(default=None, examples=["220103001"], description="9-digit SDU student ID")
    jersey_number: Jersey | None = Field(default=None, examples=[10])
    position: Position | None = Field(default=None, examples=[Position.FORWARD])


class PlayerUpdate(BaseModel):
    first_name: PersonName | None = None
    last_name: PersonName | None = None
    jersey_number: Jersey | None = None
    position: Position | None = None
    team_id: int | None = Field(default=None, gt=0, description="Transfer the player to another team")


class PlayerRead(ORMModel):
    id: int
    team_id: int
    first_name: str
    last_name: str
    full_name: str
    student_id: str | None
    jersey_number: int | None
    position: Position | None


class TeamRef(BaseModel):
    id: int
    name: str


class PlayerStats(BaseModel):
    teams: list[TeamRef] = Field(description="Current team first, then other teams the player played for")
    player_id: int
    full_name: str
    team_id: int
    tournament_id: int | None
    matches_with_events: int
    goals: int
    assists: int
    own_goals: int
    yellow_cards: int
    red_cards: int
