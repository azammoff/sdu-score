from sqlalchemy import or_, select

from app.db.models import Match, Team
from app.enums import MatchStatus
from app.errors import ConflictError
from app.schemas.team import TeamCreate, TeamUpdate
from app.services.common import changes, get_or_404


def get_team(store, team_id: int):
    return get_or_404(store.teams, team_id, "Team")


def team_matches(store, team_id: int, status: MatchStatus | None = None, tournament_id: int | None = None):
    query = select(Match).where(or_(Match.home_team_id == team_id, Match.away_team_id == team_id))
    if status:
        query = query.where(Match.status == status)
    if tournament_id:
        query = query.where(Match.tournament_id == tournament_id)
    return list(store.session.scalars(query.order_by(Match.kickoff)))


def _check_name_unique(store, name: str, exclude_id: int | None = None) -> None:
    for t in store.teams.all():
        if t.id != exclude_id and t.name.lower() == name.lower():
            raise ConflictError(f"Team named '{name}' already exists")


def list_teams(store, faculty_id: int | None = None, search: str | None = None):
    query = select(Team)
    if faculty_id:
        query = query.where(Team.faculty_id == faculty_id)
    if search:
        query = query.where(Team.name.icontains(search, autoescape=True))
    return list(store.session.scalars(query.order_by(Team.name)))


def get_team_detail(store, team_id: int) -> dict:
    team = get_team(store, team_id)
    return {
        "id": team.id,
        "name": team.name,
        "faculty_id": team.faculty_id,
        "coach_name": team.coach_name,
        "faculty": team.faculty,
        "players": team.players,
        "tournament_ids": sorted(e.tournament_id for e in team.enrollments),
    }


def create_team(store, data: TeamCreate):
    if data.faculty_id is not None:
        get_or_404(store.faculties, data.faculty_id, "Faculty")
    _check_name_unique(store, data.name)
    team = store.teams.add(name=data.name, faculty_id=data.faculty_id, coach_name=data.coach_name)
    store.commit()
    return team


def update_team(store, team_id: int, data: TeamUpdate):
    team = get_team(store, team_id)
    fields = changes(data)
    if fields.get("faculty_id") is not None:
        get_or_404(store.faculties, fields["faculty_id"], "Faculty")
    if "name" in fields:
        _check_name_unique(store, fields["name"], exclude_id=team_id)
    store.teams.update(team, **fields)
    store.commit()
    return team


def delete_team(store, team_id: int) -> None:
    """A team that already has matches is part of tournament history and cannot be deleted."""
    team = get_team(store, team_id)
    matches = team_matches(store, team_id)
    if matches:
        raise ConflictError(
            f"Team has {len(matches)} match(es) and cannot be deleted",
            details={"match_ids": [m.id for m in matches]},
        )
    for player in store.players.where(team_id=team_id):
        store.players.delete(player)
    for enrollment in store.enrollments.where(team_id=team_id):
        store.enrollments.delete(enrollment)
    store.teams.delete(team)
    store.commit()
