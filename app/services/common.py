from typing import Any

from app.errors import NotFoundError


def get_or_404(table: Any, obj_id: int, entity: str):
    obj = table.get(obj_id)
    if obj is None:
        raise NotFoundError(f"{entity} with id {obj_id} not found")
    return obj


def changes(data) -> dict:
    """Fields the client actually sent in a PATCH body."""
    return data.model_dump(exclude_unset=True)
