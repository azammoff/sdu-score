from fastapi import APIRouter, Depends, Path, Query, status

from app.deps import get_store, require_admin
from app.enums import MatchStatus, TournamentStatus
from app.schemas.match import MatchCreate, MatchRead
from app.schemas.team import TeamRead
from app.schemas.tournament import (
    EnrollmentCreate,
    StandingRow,
    TopScorerRow,
    TournamentCreate,
    TournamentDetail,
    TournamentRead,
    TournamentUpdate,
)
from app.services import matches as match_service
from app.services import stats as stats_service
from app.services import tournaments as service

router = APIRouter(prefix="/tournaments", tags=["Tournaments & Scheduling"])
admin = [Depends(require_admin)]
TournamentId = Path(gt=0, description="Tournament ID")


@router.get("", response_model=list[TournamentRead])
def list_tournaments(
    status: TournamentStatus | None = None,
    season: str | None = Query(None, pattern=r"^\d{4}(/\d{4})?$"),
    store=Depends(get_store),
):
    return service.list_tournaments(store, status, season)


@router.post("", response_model=TournamentRead, status_code=status.HTTP_201_CREATED, dependencies=admin)
def create_tournament(data: TournamentCreate, store=Depends(get_store)):
    return service.create_tournament(store, data)


@router.get("/{tournament_id}", response_model=TournamentDetail)
def get_tournament(tournament_id: int = TournamentId, store=Depends(get_store)):
    return service.get_tournament_detail(store, tournament_id)


@router.patch("/{tournament_id}", response_model=TournamentRead, dependencies=admin)
def update_tournament(data: TournamentUpdate, tournament_id: int = TournamentId, store=Depends(get_store)):
    return service.update_tournament(store, tournament_id, data)


@router.delete("/{tournament_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=admin)
def delete_tournament(tournament_id: int = TournamentId, store=Depends(get_store)):
    service.delete_tournament(store, tournament_id)


@router.post("/{tournament_id}/start", response_model=TournamentRead, dependencies=admin, summary="Close registration and start")
def start_tournament(tournament_id: int = TournamentId, store=Depends(get_store)):
    return service.start_tournament(store, tournament_id)


@router.post("/{tournament_id}/finish", response_model=TournamentRead, dependencies=admin)
def finish_tournament(tournament_id: int = TournamentId, store=Depends(get_store)):
    return service.finish_tournament(store, tournament_id)


@router.get("/{tournament_id}/teams", response_model=list[TeamRead], summary="Enrolled teams")
def list_enrolled_teams(tournament_id: int = TournamentId, store=Depends(get_store)):
    return service.list_enrolled_teams(store, tournament_id)


@router.post(
    "/{tournament_id}/teams",
    response_model=TeamRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=admin,
    summary="Enroll a team",
)
def enroll_team(data: EnrollmentCreate, tournament_id: int = TournamentId, store=Depends(get_store)):
    return service.enroll_team(store, tournament_id, data)


@router.delete(
    "/{tournament_id}/teams/{team_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=admin,
    summary="Withdraw a team",
)
def withdraw_team(tournament_id: int = TournamentId, team_id: int = Path(gt=0), store=Depends(get_store)):
    service.withdraw_team(store, tournament_id, team_id)


@router.get("/{tournament_id}/matches", response_model=list[MatchRead])
def list_tournament_matches(
    tournament_id: int = TournamentId,
    status: MatchStatus | None = None,
    stage: str | None = Query(None, max_length=40, examples=["Final"]),
    group: str | None = Query(None, max_length=10, examples=["A"]),
    store=Depends(get_store),
):
    return match_service.list_tournament_matches(store, tournament_id, status, stage, group)


@router.post(
    "/{tournament_id}/matches",
    response_model=MatchRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=admin,
    summary="Schedule a match",
)
def schedule_match(data: MatchCreate, tournament_id: int = TournamentId, store=Depends(get_store)):
    return match_service.schedule_match(store, tournament_id, data)


@router.get("/{tournament_id}/standings", response_model=list[StandingRow], summary="League table")
def get_standings(
    tournament_id: int = TournamentId,
    group: str | None = Query(None, max_length=10, description="Only this group, e.g. A"),
    stage: str | None = Query(None, max_length=40, description="Only this stage, e.g. Qualification"),
    stage_prefix: str | None = Query(None, max_length=40, description="Stages starting with this, e.g. Tour"),
    store=Depends(get_store),
):
    return stats_service.standings(store, tournament_id, group, stage, stage_prefix)


@router.get("/{tournament_id}/top-scorers", response_model=list[TopScorerRow])
def get_top_scorers(
    tournament_id: int = TournamentId, limit: int = Query(10, ge=1, le=50), store=Depends(get_store)
):
    return stats_service.top_scorers(store, tournament_id, limit)
