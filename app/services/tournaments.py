from app.enums import MatchStatus, TournamentStatus
from app.errors import BusinessRuleError, ConflictError, NotFoundError
from app.schemas.tournament import EnrollmentCreate, TournamentCreate, TournamentUpdate
from app.services.common import changes, get_or_404
from app.services.teams import get_team


def get_tournament(store, tournament_id: int):
    return get_or_404(store.tournaments, tournament_id, "Tournament")


def list_tournaments(store, status: TournamentStatus | None = None, season: str | None = None):
    items = store.tournaments.all()
    if status:
        items = [t for t in items if t.status == status]
    if season:
        items = [t for t in items if t.season == season]
    return sorted(items, key=lambda t: t.start_date, reverse=True)


def get_tournament_detail(store, tournament_id: int) -> dict:
    t = get_tournament(store, tournament_id)
    matches = store.matches.where(tournament_id=tournament_id)
    return {
        **{k: getattr(t, k) for k in ("id", "name", "season", "start_date", "end_date", "max_teams", "status")},
        "team_count": len(store.enrollments.where(tournament_id=tournament_id)),
        "match_count": len(matches),
        "finished_match_count": sum(m.status == MatchStatus.FINISHED for m in matches),
        "stages": _ordered_stages(matches),
        "groups": sorted({m.group_name for m in matches if m.group_name}),
    }


def _ordered_stages(matches) -> list[str]:
    """Stages in the order they were first played (Qualification, Tour 1, ..., Final)."""
    first_seen: dict[str, object] = {}
    for m in sorted(matches, key=lambda m: m.kickoff):
        if m.stage and m.stage not in first_seen:
            first_seen[m.stage] = m.kickoff
    return list(first_seen)


def _check_name_unique(store, name: str, season: str, exclude_id: int | None = None) -> None:
    for t in store.tournaments.all():
        if t.id != exclude_id and t.name.lower() == name.lower() and t.season == season:
            raise ConflictError(f"Tournament '{name}' already exists for season {season}")


def create_tournament(store, data: TournamentCreate):
    _check_name_unique(store, data.name, data.season)
    tournament = store.tournaments.add(**data.model_dump(), status=TournamentStatus.UPCOMING)
    store.commit()
    return tournament


def update_tournament(store, tournament_id: int, data: TournamentUpdate):
    t = get_tournament(store, tournament_id)
    fields = changes(data)
    structural = {"start_date", "end_date", "max_teams", "season"} & fields.keys()
    if structural and t.status != TournamentStatus.UPCOMING:
        raise ConflictError(f"Only the name can be changed once a tournament is {t.status}; tried: {sorted(structural)}")

    start = fields.get("start_date", t.start_date)
    end = fields.get("end_date", t.end_date)
    if end < start:
        raise BusinessRuleError("end_date must be on or after start_date")

    enrolled = len(store.enrollments.where(tournament_id=tournament_id))
    if fields.get("max_teams", t.max_teams) < enrolled:
        raise BusinessRuleError(f"max_teams cannot be lower than the {enrolled} teams already enrolled")

    outside = [m.id for m in store.matches.where(tournament_id=tournament_id) if not start <= m.kickoff.date() <= end]
    if outside:
        raise BusinessRuleError("New dates would leave scheduled matches outside the tournament", {"match_ids": outside})

    _check_name_unique(store, fields.get("name", t.name), fields.get("season", t.season), exclude_id=tournament_id)
    store.tournaments.update(t, **fields)
    store.commit()
    return t


def delete_tournament(store, tournament_id: int) -> None:
    t = get_tournament(store, tournament_id)
    matches = store.matches.where(tournament_id=tournament_id)
    played = [m.id for m in matches if m.status in (MatchStatus.LIVE, MatchStatus.FINISHED)]
    if played:
        raise ConflictError("Tournament has played matches and cannot be deleted", {"match_ids": played})
    for m in matches:
        store.matches.delete(m)
    for e in store.enrollments.where(tournament_id=tournament_id):
        store.enrollments.delete(e)
    store.tournaments.delete(t)
    store.commit()


def start_tournament(store, tournament_id: int):
    t = get_tournament(store, tournament_id)
    if t.status != TournamentStatus.UPCOMING:
        raise ConflictError(f"Tournament is already {t.status}")
    enrolled = len(store.enrollments.where(tournament_id=tournament_id))
    if enrolled < 2:
        raise BusinessRuleError(f"At least 2 teams are needed to start; {enrolled} enrolled")
    store.tournaments.update(t, status=TournamentStatus.ONGOING)
    store.commit()
    return t


def finish_tournament(store, tournament_id: int):
    t = get_tournament(store, tournament_id)
    if t.status != TournamentStatus.ONGOING:
        raise ConflictError(f"Only ongoing tournaments can be finished; this one is {t.status}")
    pending = [
        m.id
        for m in store.matches.where(tournament_id=tournament_id)
        if m.status in (MatchStatus.SCHEDULED, MatchStatus.LIVE)
    ]
    if pending:
        raise ConflictError(f"{len(pending)} match(es) are still scheduled or live", {"match_ids": pending})
    store.tournaments.update(t, status=TournamentStatus.FINISHED)
    store.commit()
    return t


def list_enrolled_teams(store, tournament_id: int):
    get_tournament(store, tournament_id)
    teams = [store.teams.get(e.team_id) for e in store.enrollments.where(tournament_id=tournament_id)]
    return sorted(teams, key=lambda t: t.name)


def is_enrolled(store, tournament_id: int, team_id: int) -> bool:
    return bool(store.enrollments.where(tournament_id=tournament_id, team_id=team_id))


def enroll_team(store, tournament_id: int, data: EnrollmentCreate):
    t = get_tournament(store, tournament_id)
    team = get_team(store, data.team_id)
    if t.status != TournamentStatus.UPCOMING:
        raise ConflictError(f"Registration is closed: tournament is {t.status}")
    if is_enrolled(store, tournament_id, team.id):
        raise ConflictError(f"Team '{team.name}' is already enrolled")
    enrolled = len(store.enrollments.where(tournament_id=tournament_id))
    if enrolled >= t.max_teams:
        raise ConflictError(f"Tournament is full ({t.max_teams} teams)")
    store.enrollments.add(tournament_id=tournament_id, team_id=team.id)
    store.commit()
    return team


def withdraw_team(store, tournament_id: int, team_id: int) -> None:
    t = get_tournament(store, tournament_id)
    team = get_team(store, team_id)
    enrollment = store.enrollments.where(tournament_id=tournament_id, team_id=team_id)
    if not enrollment:
        raise NotFoundError(f"Team '{team.name}' is not enrolled in this tournament")
    if t.status != TournamentStatus.UPCOMING:
        raise ConflictError(f"Teams cannot withdraw once the tournament is {t.status}")
    scheduled = [
        m.id
        for m in store.matches.where(tournament_id=tournament_id)
        if team_id in (m.home_team_id, m.away_team_id) and m.status != MatchStatus.CANCELLED
    ]
    if scheduled:
        raise ConflictError("Cancel or delete this team's scheduled matches first", {"match_ids": scheduled})
    store.enrollments.delete(enrollment[0])
    store.commit()
