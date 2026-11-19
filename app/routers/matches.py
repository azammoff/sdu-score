from datetime import datetime

from fastapi import APIRouter, Depends, Path, Query, status

from app.deps import get_store, require_admin
from app.enums import EventType, MatchStatus
from app.schemas.common import to_naive_utc
from app.schemas.match import EventCreate, EventCreateResult, EventRead, MatchDetail, MatchRead, MatchUpdate
from app.services import events as event_service
from app.services import matches as service

router = APIRouter(prefix="/matches", tags=["Matches & Live Events"])
admin = [Depends(require_admin)]
MatchId = Path(gt=0, description="Match ID")


@router.get("", response_model=list[MatchRead], summary="Search matches")
def list_matches(
    tournament_id: int | None = Query(None, gt=0),
    team_id: int | None = Query(None, gt=0),
    status: MatchStatus | None = None,
    date_from: datetime | None = Query(None, description="Kickoff on or after"),
    date_to: datetime | None = Query(None, description="Kickoff on or before"),
    stage: str | None = Query(None, max_length=40),
    group: str | None = Query(None, max_length=10),
    newest_first: bool = Query(False, description="Latest matches first"),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    store=Depends(get_store),
):
    date_from = to_naive_utc(date_from) if date_from else None
    date_to = to_naive_utc(date_to) if date_to else None
    return service.list_matches(
        store, tournament_id, team_id, status, date_from, date_to, stage, group, newest_first, limit, offset
    )


@router.get("/{match_id}", response_model=MatchDetail, summary="Match with teams and events")
def get_match(match_id: int = MatchId, store=Depends(get_store)):
    return service.get_match_detail(store, match_id)


@router.patch("/{match_id}", response_model=MatchRead, dependencies=admin, summary="Reschedule a match")
def update_match(data: MatchUpdate, match_id: int = MatchId, store=Depends(get_store)):
    return service.update_match(store, match_id, data)


@router.delete("/{match_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=admin)
def delete_match(match_id: int = MatchId, store=Depends(get_store)):
    service.delete_match(store, match_id)


@router.post("/{match_id}/start", response_model=MatchRead, dependencies=admin, summary="Kick off (scheduled → live)")
def start_match(match_id: int = MatchId, store=Depends(get_store)):
    return service.start_match(store, match_id)


@router.post("/{match_id}/finish", response_model=MatchRead, dependencies=admin, summary="Final whistle (live → finished)")
def finish_match(match_id: int = MatchId, store=Depends(get_store)):
    return service.finish_match(store, match_id)


@router.post("/{match_id}/cancel", response_model=MatchRead, dependencies=admin, summary="Cancel a scheduled match")
def cancel_match(match_id: int = MatchId, store=Depends(get_store)):
    return service.cancel_match(store, match_id)


@router.get("/{match_id}/events", response_model=list[EventRead])
def list_events(match_id: int = MatchId, type: EventType | None = None, store=Depends(get_store)):
    return event_service.list_events(store, match_id, type)


@router.post(
    "/{match_id}/events",
    response_model=EventCreateResult,
    status_code=status.HTTP_201_CREATED,
    dependencies=admin,
    summary="Record a goal or card",
)
def record_event(data: EventCreate, match_id: int = MatchId, store=Depends(get_store)):
    return event_service.record_event(store, match_id, data)


@router.delete(
    "/{match_id}/events/{event_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=admin,
    summary="Remove a wrongly recorded event",
)
def delete_event(match_id: int = MatchId, event_id: int = Path(gt=0), store=Depends(get_store)):
    event_service.delete_event(store, match_id, event_id)
