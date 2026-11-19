from fastapi import APIRouter, Depends, Path, Query, status

from app.deps import get_store, require_admin
from app.enums import Position
from app.schemas.match import MatchRead
from app.schemas.player import PlayerRead, PlayerStats, PlayerUpdate
from app.services import players as service
from app.services import stats as stats_service

router = APIRouter(prefix="/players", tags=["Players"])
admin = [Depends(require_admin)]
PlayerId = Path(gt=0, description="Player ID")


@router.get("", response_model=list[PlayerRead])
def list_players(
    team_id: int | None = Query(None, gt=0),
    position: Position | None = None,
    search: str | None = Query(None, min_length=1, max_length=100, description="Part of the player's name"),
    store=Depends(get_store),
):
    return service.list_players(store, team_id, position, search)


@router.get("/{player_id}", response_model=PlayerRead)
def get_player(player_id: int = PlayerId, store=Depends(get_store)):
    return service.get_player(store, player_id)


@router.patch("/{player_id}", response_model=PlayerRead, dependencies=admin, summary="Update or transfer a player")
def update_player(data: PlayerUpdate, player_id: int = PlayerId, store=Depends(get_store)):
    return service.update_player(store, player_id, data)


@router.delete("/{player_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=admin)
def delete_player(player_id: int = PlayerId, store=Depends(get_store)):
    service.delete_player(store, player_id)


@router.get("/{player_id}/matches", response_model=list[MatchRead], summary="Matches the player took part in")
def list_player_matches(player_id: int = PlayerId, store=Depends(get_store)):
    return service.player_matches(store, player_id)


@router.get("/{player_id}/stats", response_model=PlayerStats)
def get_player_stats(player_id: int = PlayerId, tournament_id: int | None = Query(None, gt=0), store=Depends(get_store)):
    return stats_service.player_stats(store, player_id, tournament_id)
