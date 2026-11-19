from datetime import datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from app.config import settings
from app.db.models import Match
from app.enums import EventType, MatchStatus, TournamentStatus
from app.errors import BusinessRuleError, ConflictError
from app.schemas.match import MatchCreate, MatchUpdate
from app.services.common import changes, get_or_404
from app.services.teams import get_team, team_matches
from app.services.tournaments import get_tournament, is_enrolled


def get_match(store, match_id: int):
    return get_or_404(store.matches, match_id, "Match")


def list_matches(
    store,
    tournament_id: int | None = None,
    team_id: int | None = None,
    status: MatchStatus | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    stage: str | None = None,
    group_name: str | None = None,
    newest_first: bool = False,
    limit: int | None = None,
    offset: int = 0,
):
    query = select(Match).options(selectinload(Match.home_team), selectinload(Match.away_team))
    if tournament_id:
        query = query.where(Match.tournament_id == tournament_id)
    if team_id:
        query = query.where(or_(Match.home_team_id == team_id, Match.away_team_id == team_id))
    if status:
        query = query.where(Match.status == status)
    if date_from:
        query = query.where(Match.kickoff >= date_from)
    if date_to:
        query = query.where(Match.kickoff <= date_to)
    if stage:
        query = query.where(Match.stage == stage)
    if group_name:
        query = query.where(Match.group_name == group_name.upper())
    order = (Match.kickoff.desc(), Match.id.desc()) if newest_first else (Match.kickoff, Match.id)
    query = query.order_by(*order).offset(offset)
    if limit:
        query = query.limit(limit)
    return list(store.session.scalars(query))


def list_tournament_matches(
    store, tournament_id: int, status: MatchStatus | None = None, stage: str | None = None, group_name: str | None = None
):
    get_tournament(store, tournament_id)
    return list_matches(store, tournament_id=tournament_id, status=status, stage=stage, group_name=group_name)


def get_match_detail(store, match_id: int):
    """The match with its teams and events (loaded through the model relationships)."""
    return get_match(store, match_id)


def _check_kickoff(store, tournament, home_id: int, away_id: int, kickoff: datetime, exclude_id: int | None = None):
    if not tournament.start_date <= kickoff.date() <= tournament.end_date:
        raise BusinessRuleError(
            f"Kickoff must be between {tournament.start_date} and {tournament.end_date} (tournament dates)"
        )
    gap = timedelta(hours=settings.min_hours_between_team_matches)
    for team_id in (home_id, away_id):
        for other in team_matches(store, team_id):
            if other.id == exclude_id or other.status == MatchStatus.CANCELLED:
                continue
            if abs(other.kickoff - kickoff) < gap:
                team = store.teams.get(team_id)
                raise ConflictError(
                    f"'{team.name}' already plays match {other.id} at {other.kickoff:%Y-%m-%d %H:%M}; "
                    f"matches must be at least {settings.min_hours_between_team_matches}h apart"
                )


def schedule_match(store, tournament_id: int, data: MatchCreate):
    tournament = get_tournament(store, tournament_id)
    if tournament.status == TournamentStatus.FINISHED:
        raise ConflictError("Cannot schedule matches in a finished tournament")
    for team_id in (data.home_team_id, data.away_team_id):
        team = get_team(store, team_id)
        if not is_enrolled(store, tournament_id, team_id):
            raise BusinessRuleError(f"Team '{team.name}' is not enrolled in '{tournament.name}'")
    _check_kickoff(store, tournament, data.home_team_id, data.away_team_id, data.kickoff)
    match = store.matches.add(tournament_id=tournament_id, **data.model_dump(), status=MatchStatus.SCHEDULED)
    store.commit()
    return match


def update_match(store, match_id: int, data: MatchUpdate):
    """Reschedule a match (new kickoff and/or venue). Only scheduled matches can change."""
    m = get_match(store, match_id)
    if m.status != MatchStatus.SCHEDULED:
        raise ConflictError(f"Only scheduled matches can be edited; this one is {m.status}")
    fields = changes(data)
    if fields.get("kickoff"):
        tournament = get_tournament(store, m.tournament_id)
        _check_kickoff(store, tournament, m.home_team_id, m.away_team_id, fields["kickoff"], exclude_id=m.id)
    fields = {k: v for k, v in fields.items() if v is not None}
    store.matches.update(m, **fields)
    store.commit()
    return m


def delete_match(store, match_id: int) -> None:
    m = get_match(store, match_id)
    if m.status in (MatchStatus.LIVE, MatchStatus.FINISHED):
        raise ConflictError(f"A {m.status} match cannot be deleted")
    store.matches.delete(m)
    store.commit()


def _transition(store, match_id: int, allowed_from: MatchStatus, to: MatchStatus):
    m = get_match(store, match_id)
    if m.status != allowed_from:
        raise ConflictError(f"Match is {m.status}; it must be {allowed_from} to become {to}")
    return m


def start_match(store, match_id: int):
    m = _transition(store, match_id, MatchStatus.SCHEDULED, MatchStatus.LIVE)
    tournament = get_tournament(store, m.tournament_id)
    if tournament.status != TournamentStatus.ONGOING:
        raise ConflictError(f"Tournament '{tournament.name}' is {tournament.status}; start the tournament first")
    store.matches.update(m, status=MatchStatus.LIVE, home_score=0, away_score=0)
    store.commit()
    return m


def finish_match(store, match_id: int):
    m = _transition(store, match_id, MatchStatus.LIVE, MatchStatus.FINISHED)
    store.matches.update(m, status=MatchStatus.FINISHED)
    store.commit()
    return m


def cancel_match(store, match_id: int):
    m = _transition(store, match_id, MatchStatus.SCHEDULED, MatchStatus.CANCELLED)
    store.matches.update(m, status=MatchStatus.CANCELLED)
    store.commit()
    return m


def recompute_score(store, match) -> None:
    """The score is always derived from the recorded goal events, never typed in by hand."""
    home = away = 0
    for e in store.events.where(match_id=match.id):
        if e.type == EventType.GOAL:
            home += e.team_id == match.home_team_id
            away += e.team_id == match.away_team_id
        elif e.type == EventType.OWN_GOAL:
            home += e.team_id == match.away_team_id
            away += e.team_id == match.home_team_id
    store.matches.update(match, home_score=home, away_score=away)
