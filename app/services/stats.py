from sqlalchemy import func, select

from app.db.models import Match, MatchEvent, Player, Team
from app.enums import EventType, MatchStatus
from app.services.players import full_name, get_player
from app.services.teams import get_team, team_matches
from app.services.tournaments import get_tournament

POINTS_WIN, POINTS_DRAW = 3, 1


def _empty_row() -> dict:
    return {"played": 0, "wins": 0, "draws": 0, "losses": 0, "goals_for": 0, "goals_against": 0}


def _apply_result(row: dict, scored: int, conceded: int) -> None:
    row["played"] += 1
    row["goals_for"] += scored
    row["goals_against"] += conceded
    if scored > conceded:
        row["wins"] += 1
    elif scored == conceded:
        row["draws"] += 1
    else:
        row["losses"] += 1


def _finalize(row: dict) -> dict:
    row["goal_difference"] = row["goals_for"] - row["goals_against"]
    row["points"] = row["wins"] * POINTS_WIN + row["draws"] * POINTS_DRAW
    return row


def standings(
    store, tournament_id: int, group_name: str | None = None, stage: str | None = None, stage_prefix: str | None = None
) -> list[dict]:
    """League table: 3 points per win, 1 per draw; ties broken by goal difference, then goals scored.

    With `group_name` / `stage` only that group's or stage's matches count (e.g. a cup's Group A).
    """
    get_tournament(store, tournament_id)
    filters = {"tournament_id": tournament_id, "status": MatchStatus.FINISHED}
    if group_name:
        filters["group_name"] = group_name.upper()
    if stage:
        filters["stage"] = stage
    if group_name or stage or stage_prefix:
        rows = {}
    else:
        rows = {e.team_id: _empty_row() for e in store.enrollments.where(tournament_id=tournament_id)}
    for m in store.matches.where(**filters):
        if stage_prefix and not (m.stage or "").lower().startswith(stage_prefix.lower()):
            continue
        _apply_result(rows.setdefault(m.home_team_id, _empty_row()), m.home_score, m.away_score)
        _apply_result(rows.setdefault(m.away_team_id, _empty_row()), m.away_score, m.home_score)

    table = []
    for team_id, row in rows.items():
        team = store.teams.get(team_id)
        table.append({"team_id": team_id, "team_name": team.name if team else "?", **_finalize(row)})
    table.sort(key=lambda r: (-r["points"], -r["goal_difference"], -r["goals_for"], r["team_name"]))
    return [{"position": i, **r} for i, r in enumerate(table, start=1)]


def top_scorers(store, tournament_id: int | None = None, limit: int = 10, team_id: int | None = None) -> list[dict]:
    """Goals (not own goals) in live and finished matches, with assists, grouped per player in SQL.

    Without `tournament_id` it covers all tournaments (all-time); `team_id` limits it to one team.
    """
    if tournament_id:
        get_tournament(store, tournament_id)
    if team_id:
        get_team(store, team_id)
    counted_matches = select(Match.id).where(Match.status.in_([MatchStatus.LIVE, MatchStatus.FINISHED]))
    if tournament_id:
        counted_matches = counted_matches.where(Match.tournament_id == tournament_id)
    # Events remember the team the player played for in that match, so transfers are counted correctly.
    goal_filter = [MatchEvent.type == EventType.GOAL, MatchEvent.match_id.in_(counted_matches)]
    if team_id:
        goal_filter.append(MatchEvent.team_id == team_id)
    goals = (
        select(MatchEvent.player_id, func.count().label("goals"))
        .where(*goal_filter)
        .group_by(MatchEvent.player_id)
        .subquery()
    )
    assists = (
        select(MatchEvent.assist_player_id.label("player_id"), func.count().label("assists"))
        .where(*goal_filter, MatchEvent.assist_player_id.is_not(None))
        .group_by(MatchEvent.assist_player_id)
        .subquery()
    )
    player_name = func.concat(Player.first_name, " ", Player.last_name)
    assist_count = func.coalesce(assists.c.assists, 0)
    query = (
        select(Player.id, player_name, Team.id, Team.name, goals.c.goals, assist_count)
        .join(goals, goals.c.player_id == Player.id)
        .outerjoin(assists, assists.c.player_id == Player.id)
        .join(Team, Team.id == Player.team_id)
        .order_by(goals.c.goals.desc(), assist_count.desc(), player_name)
        .limit(limit)
    )
    keys = ("player_id", "player_name", "team_id", "team_name", "goals", "assists")
    rows = [{"rank": i, **dict(zip(keys, row))} for i, row in enumerate(store.session.execute(query), start=1)]
    if team_id:  # show the team they scored for, not where they play now
        team = store.teams.get(team_id)
        for row in rows:
            row.update(team_id=team.id, team_name=team.name)
    return rows


def team_stats(store, team_id: int, tournament_id: int | None = None) -> dict:
    team = get_team(store, team_id)
    if tournament_id:
        get_tournament(store, tournament_id)
    row = _empty_row()
    clean_sheets = 0
    for m in team_matches(store, team_id, status=MatchStatus.FINISHED, tournament_id=tournament_id):
        home = m.home_team_id == team_id
        scored, conceded = (m.home_score, m.away_score) if home else (m.away_score, m.home_score)
        _apply_result(row, scored, conceded)
        clean_sheets += conceded == 0

    match_ids = {m.id for m in team_matches(store, team_id, tournament_id=tournament_id)}
    cards = [e for e in store.events.where(team_id=team_id) if e.match_id in match_ids]
    return {
        "team_id": team.id,
        "team_name": team.name,
        "tournament_id": tournament_id,
        **_finalize(row),
        "clean_sheets": clean_sheets,
        "yellow_cards": sum(e.type == EventType.YELLOW_CARD for e in cards),
        "red_cards": sum(e.type == EventType.RED_CARD for e in cards),
    }


def player_stats(store, player_id: int, tournament_id: int | None = None) -> dict:
    player = get_player(store, player_id)
    if tournament_id:
        get_tournament(store, tournament_id)
        allowed = {m.id for m in store.matches.where(tournament_id=tournament_id)}
    else:
        allowed = None

    def keep(e) -> bool:
        return allowed is None or e.match_id in allowed

    own = [e for e in store.events.where(player_id=player_id) if keep(e)]
    assists = [e for e in store.events.where(assist_player_id=player_id) if keep(e)]
    team_ids = list(dict.fromkeys([player.team_id] + [e.team_id for e in sorted(own + assists, key=lambda e: -e.match_id)]))
    return {
        "teams": [{"id": t.id, "name": t.name} for t in (store.teams.get(i) for i in team_ids) if t],
        "player_id": player.id,
        "full_name": full_name(player),
        "team_id": player.team_id,
        "tournament_id": tournament_id,
        "matches_with_events": len({e.match_id for e in own + assists}),
        "goals": sum(e.type == EventType.GOAL for e in own),
        "assists": len(assists),
        "own_goals": sum(e.type == EventType.OWN_GOAL for e in own),
        "yellow_cards": sum(e.type == EventType.YELLOW_CARD for e in own),
        "red_cards": sum(e.type == EventType.RED_CARD for e in own),
    }
