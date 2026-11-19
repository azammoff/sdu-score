from fastapi import APIRouter, Depends, Path, Query, status

from app.deps import get_store, require_admin
from app.enums import MatchStatus, Position
from app.schemas.match import MatchRead
from app.schemas.player import PlayerCreate, PlayerRead
from app.schemas.team import TeamCreate, TeamDetail, TeamRead, TeamStats, TeamUpdate
from app.schemas.tournament import TopScorerRow
from app.services import players as player_service
from app.services import stats as stats_service
from app.services import teams as service

router = APIRouter(prefix="/teams", tags=["Teams & Rosters"])
admin = [Depends(require_admin)]
TeamId = Path(gt=0, description="Team ID")


@router.get("", response_model=list[TeamRead])
def list_teams(
    faculty_id: int | None = Query(None, gt=0),
    search: str | None = Query(None, min_length=1, max_length=60, description="Part of the team name"),
    store=Depends(get_store),
):
    return service.list_teams(store, faculty_id, search)


@router.post("", response_model=TeamRead, status_code=status.HTTP_201_CREATED, dependencies=admin)
def create_team(data: TeamCreate, store=Depends(get_store)):
    return service.create_team(store, data)


@router.get("/{team_id}", response_model=TeamDetail, summary="Team with faculty, roster and tournaments")
def get_team(team_id: int = TeamId, store=Depends(get_store)):
    return service.get_team_detail(store, team_id)


@router.patch("/{team_id}", response_model=TeamRead, dependencies=admin)
def update_team(data: TeamUpdate, team_id: int = TeamId, store=Depends(get_store)):
    return service.update_team(store, team_id, data)


@router.delete("/{team_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=admin)
def delete_team(team_id: int = TeamId, store=Depends(get_store)):
    service.delete_team(store, team_id)


@router.get("/{team_id}/players", response_model=list[PlayerRead], summary="Team roster")
def list_team_players(team_id: int = TeamId, position: Position | None = None, store=Depends(get_store)):
    return player_service.list_team_players(store, team_id, position)


@router.post(
    "/{team_id}/players",
    response_model=PlayerRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=admin,
    summary="Register a player in the team",
)
def add_player(data: PlayerCreate, team_id: int = TeamId, store=Depends(get_store)):
    return player_service.add_player(store, team_id, data)


@router.get("/{team_id}/matches", response_model=list[MatchRead])
def list_team_matches(
    team_id: int = TeamId,
    status: MatchStatus | None = None,
    tournament_id: int | None = Query(None, gt=0),
    store=Depends(get_store),
):
    service.get_team(store, team_id)
    return service.team_matches(store, team_id, status, tournament_id)


@router.get("/{team_id}/top-scorers", response_model=list[TopScorerRow], summary="Team's best scorers")
def get_team_top_scorers(
    team_id: int = TeamId,
    tournament_id: int | None = Query(None, gt=0),
    limit: int = Query(10, ge=1, le=100),
    store=Depends(get_store),
):
    return stats_service.top_scorers(store, tournament_id, limit, team_id=team_id)


@router.get("/{team_id}/stats", response_model=TeamStats)
def get_team_stats(team_id: int = TeamId, tournament_id: int | None = Query(None, gt=0), store=Depends(get_store)):
    return stats_service.team_stats(store, team_id, tournament_id)
