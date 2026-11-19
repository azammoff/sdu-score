from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from app.schemas.common import ORMModel

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=100)]
Code = Annotated[str, StringConstraints(strip_whitespace=True, to_upper=True, pattern=r"^[A-Za-z]{2,10}$")]


class FacultyCreate(BaseModel):
    name: Name = Field(examples=["Engineering and Natural Sciences"])
    code: Code = Field(examples=["ENS"], description="2-10 letters, stored upper-case")


class FacultyUpdate(BaseModel):
    name: Name | None = None
    code: Code | None = None


class FacultyRead(ORMModel):
    id: int
    name: str
    code: str
