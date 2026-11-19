from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


def to_naive_utc(value: datetime) -> datetime:
    """Store all datetimes as naive UTC so they compare safely."""
    if value.tzinfo is not None:
        return value.astimezone(UTC).replace(tzinfo=None)
    return value
