from sqlalchemy import func, select

from app.config import settings
from app.db.models import Player
from app.enums import MatchStatus, Position
from app.errors import BusinessRuleError, ConflictError
from app.schemas.player import PlayerCreate, PlayerUpdate
from app.services.common import changes, get_or_404
from app.services.teams import get_team, team_matches


def get_player(store, player_id: int):
    return get_or_404(store.players, player_id, "Player")


def full_name(player) -> str:
    return f"{player.first_name} {player.last_name}"


def list_players(store, team_id: int | None = None, position: Position | None = None, search: str | None = None):
    query = select(Player)
    if team_id:
        query = query.where(Player.team_id == team_id)
    if position:
        query = query.where(Player.position == position)
    if search:
        query = query.where(
            func.concat(Player.first_name, " ", Player.last_name).icontains(search, autoescape=True)
        )
    return list(store.session.scalars(query.order_by(Player.team_id, Player.jersey_number)))


def list_team_players(store, team_id: int, position: Position | None = None):
    get_team(store, team_id)
    return list_players(store, team_id=team_id, position=position)


def _check_roster_space(store, team) -> None:
    if len(store.players.where(team_id=team.id)) >= settings.roster_max_players:
        raise BusinessRuleError(f"Team '{team.name}' already has the maximum of {settings.roster_max_players} players")


def _check_jersey_free(store, team, jersey: int | None, exclude_id: int | None = None) -> None:
    if jersey is None:
        return
    for p in store.players.where(team_id=team.id):
        if p.id != exclude_id and p.jersey_number == jersey:
            raise ConflictError(f"Jersey #{jersey} is already taken in '{team.name}' by {full_name(p)}")


def _has_live_match(store, team_id: int) -> bool:
    return bool(team_matches(store, team_id, status=MatchStatus.LIVE))


def add_player(store, team_id: int, data: PlayerCreate):
    team = get_team(store, team_id)
    _check_roster_space(store, team)
    _check_jersey_free(store, team, data.jersey_number)
    existing = store.players.where(student_id=data.student_id) if data.student_id else []
    if existing:
        other_team = store.teams.get(existing[0].team_id)
        raise ConflictError(f"Student {data.student_id} is already registered for team '{other_team.name}'")
    player = store.players.add(team_id=team_id, **data.model_dump())
    store.commit()
    return player


def update_player(store, player_id: int, data: PlayerUpdate):
    player = get_player(store, player_id)
    fields = changes(data)
    target_team = get_team(store, fields.get("team_id", player.team_id))

    if target_team.id != player.team_id:
        if _has_live_match(store, player.team_id) or _has_live_match(store, target_team.id):
            raise ConflictError("Players cannot be transferred while either team is playing a live match")
        _check_roster_space(store, target_team)

    jersey = fields.get("jersey_number", player.jersey_number)
    if target_team.id != player.team_id or "jersey_number" in fields:
        _check_jersey_free(store, target_team, jersey, exclude_id=player.id)

    store.players.update(player, **fields)
    store.commit()
    return player


def player_matches(store, player_id: int):
    """Matches in which the player scored, assisted or was booked, newest first."""
    from app.db.models import Match, MatchEvent  # local import keeps the module header small

    get_player(store, player_id)
    involved = select(MatchEvent.match_id).where(
        (MatchEvent.player_id == player_id) | (MatchEvent.assist_player_id == player_id)
    )
    query = select(Match).where(Match.id.in_(involved)).order_by(Match.kickoff.desc())
    return list(store.session.scalars(query))


def delete_player(store, player_id: int) -> None:
    player = get_player(store, player_id)
    events = store.events.where(player_id=player_id) + store.events.where(assist_player_id=player_id)
    if events:
        raise ConflictError(
            f"{full_name(player)} appears in {len(events)} match event(s) and cannot be deleted; transfer them instead"
        )
    store.players.delete(player)
    store.commit()
