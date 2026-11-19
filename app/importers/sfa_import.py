"""Import SDU Football Association match history from the Telegram channel export.

    python -m app.importers.sfa_import data/sfa_channel.json --reset

Historical matches are already finished, so they are written straight to the database
(the live-match rules in app/services only apply to matches recorded through the API).
"""

import argparse
import collections
import difflib
from datetime import date

from sqlalchemy import text

from app.db.base import Base
from app.db.models import Enrollment, Match, MatchEvent, Player, Team, Tournament
from app.db.session import SessionLocal
from app.enums import EventType, MatchStatus, TournamentStatus
from app.importers.people import cluster_people, name_tokens
from app.importers.sfa_parser import ParsedMatch, parse_export, team_key

COMPETITION_NAMES = {"SFC": "SDU Football Cup", "SFL": "SDU Football League"}
VENUE = "SDU Arena"


def _display_name(variants: collections.Counter) -> str:
    """Pick the most common spelling, preferring one that isn't ALL CAPS."""
    ranked = [name for name, _ in variants.most_common()]
    for name in ranked:
        if not name.isupper() or len(name) <= 4:
            return name
    return ranked[0].title()


def _player_display_name(variants: collections.Counter) -> str:
    """Most common spelling among proper 2-3 word names (falls back to the most common one)."""
    proper = collections.Counter({n: c for n, c in variants.items() if 2 <= len(n.split()) <= 3 and not any(ch.isdigit() for ch in n)})
    return (proper or variants).most_common(1)[0][0]


def _merge_team_typos(counts: collections.Counter) -> dict[str, str]:
    """'evoltuion' -> 'evolution': a rare key one or two letters away from a much more common one."""
    aliases = {}
    common = [k for k, c in counts.items() if c >= 5]
    for key, count in counts.items():
        if count > 2 or len(key) < 5:
            continue
        for other in common:
            if other != key and len(other) == len(key) and difflib.SequenceMatcher(None, key, other).ratio() >= 0.85:
                aliases[key] = other
                break
    return aliases


def _split_name(full: str) -> tuple[str, str]:
    parts = full.split()
    return parts[0], " ".join(parts[1:])


def reset(session) -> None:
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    session.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


def import_matches(session, parsed: list[ParsedMatch]) -> dict:
    stats = collections.Counter()

    # ---- teams (one row per club across all seasons; obvious typos merged)
    aliases = _merge_team_typos(collections.Counter(team_key(n) for m in parsed for n in (m.home, m.away)))

    def club_key(name: str) -> str:
        key = team_key(name)
        return aliases.get(key, key)

    team_names: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for m in parsed:
        team_names[club_key(m.home)][m.home] += 1
        team_names[club_key(m.away)][m.away] += 1
    teams: dict[str, Team] = {}
    for key, variants in sorted(team_names.items(), key=lambda kv: _display_name(kv[1]).lower()):
        name = _display_name(variants)
        if any(t.name.lower() == name.lower() for t in teams.values()):
            name = f"{name} ({key})"
        teams[key] = Team(name=name[:60])
    session.add_all(teams.values())
    session.flush()

    # ---- tournaments
    by_tournament: dict[tuple[str, int], list[ParsedMatch]] = collections.defaultdict(list)
    for m in parsed:
        by_tournament[(m.competition, m.season)].append(m)
    tournaments: dict[tuple[str, int], Tournament] = {}
    for (comp, season), matches in sorted(by_tournament.items()):
        days = [m.played_at.date() for m in matches]
        clubs = {club_key(m.home) for m in matches} | {club_key(m.away) for m in matches}
        t = Tournament(
            name=COMPETITION_NAMES[comp],
            season=str(season),
            start_date=min(days),
            end_date=max(max(days), min(days)),
            max_teams=max(2, min(64, len(clubs))),
            status=TournamentStatus.FINISHED if max(days) < date.today() else TournamentStatus.ONGOING,
        )
        tournaments[(comp, season)] = t
        session.add(t)
        session.flush()
        session.add_all(Enrollment(tournament_id=t.id, team_id=teams[k].id) for k in sorted(clubs))

    # ---- players: one row per person (see app/importers/people.py), current team = last team played for
    appearances: list[tuple[tuple[str, str], ParsedMatch]] = []
    for m in parsed:
        for e in m.events:
            if not e.side:
                continue
            club = club_key(m.home if e.side == "home" else m.away)
            for name in (e.player, e.assist if e.type == "goal" else None):
                if name and name_tokens(name) and club_key(name) not in team_names:
                    appearances.append(((club, name), m))
    person_of = cluster_people({a for a, _ in appearances})
    variants: dict[tuple[str, str], collections.Counter] = collections.defaultdict(collections.Counter)
    last_club: dict[tuple[str, str], tuple] = {}
    for (club, name), m in appearances:
        person = person_of[(club, name)]
        variants[person][name] += 1
        if person not in last_club or m.played_at >= last_club[person][0]:
            last_club[person] = (m.played_at, club)
    players: dict[tuple[str, str], Player] = {}
    for person, names in variants.items():
        first, last = _split_name(_player_display_name(names)[:100])
        players[person] = Player(team_id=teams[last_club[person][1]].id, first_name=first[:50], last_name=last[:50])
    session.add_all(players.values())
    session.flush()

    def player_for(club: str | None, name: str | None) -> Player | None:
        if not club or not name or (club, name) not in person_of:
            return None
        return players[person_of[(club, name)]]

    # ---- matches and events
    seen = set()
    for m in sorted(parsed, key=lambda m: m.played_at):
        home, away = teams[club_key(m.home)], teams[club_key(m.away)]
        dedupe = (m.competition, m.season, home.id, away.id, m.home_score, m.away_score, m.stage, m.leg)
        if dedupe in seen:
            stats["duplicate_matches_skipped"] += 1
            continue
        seen.add(dedupe)
        match = Match(
            tournament_id=tournaments[(m.competition, m.season)].id,
            home_team_id=home.id,
            away_team_id=away.id,
            kickoff=m.played_at,
            venue=VENUE,
            status=MatchStatus.FINISHED,
            home_score=m.home_score,
            away_score=m.away_score,
            home_penalties=m.home_penalties,
            away_penalties=m.away_penalties,
            stage=m.stage,
            group_name=m.group,
            leg=m.leg,
            source_post_id=m.post_id,
        )
        session.add(match)
        session.flush()
        stats["matches"] += 1
        for e in m.events:
            club = club_key(m.home if e.side == "home" else m.away) if e.side else None
            player = player_for(club, e.player)
            if player is None:
                stats["events_skipped_unknown_team"] += 1
                continue
            assist = player_for(club, e.assist) if e.type == "goal" else None
            if assist is player:
                assist = None
            session.add(MatchEvent(
                match_id=match.id,
                type=EventType(e.type),
                minute=e.minute,
                player_id=player.id,
                team_id=teams[club].id,  # the team the player played for in this match
                assist_player_id=assist.id if assist else None,
                is_auto=False,
            ))
            stats["events"] += 1
    stats.update(teams=len(teams), players=len(players), tournaments=len(tournaments))
    return dict(stats)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("path", help="Telegram export result.json")
    parser.add_argument("--reset", action="store_true", help="delete ALL existing data before importing")
    args = parser.parse_args()

    parsed = parse_export(args.path)
    with SessionLocal() as session:
        if args.reset:
            reset(session)
        elif session.query(Match).first() is not None:
            raise SystemExit("The database already has matches. Re-run with --reset to replace everything.")
        stats = import_matches(session, parsed)
        session.commit()
    for key, value in sorted(stats.items()):
        print(f"{key:>30}: {value}")


if __name__ == "__main__":
    main()
