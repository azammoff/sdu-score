"""Demo data so Swagger has something to show right away.

It goes through the real services, so every business rule is applied to it too.
Run once after `alembic upgrade head`:  python -m app.seed
"""

from datetime import date, datetime

from app.enums import EventType, Position
from app.schemas.faculty import FacultyCreate
from app.schemas.match import EventCreate, MatchCreate
from app.schemas.player import PlayerCreate
from app.schemas.team import TeamCreate
from app.schemas.tournament import EnrollmentCreate, TournamentCreate
from app.services import events, faculties, matches, players, teams, tournaments

FACULTIES = [
    ("Engineering and Natural Sciences", "ENS"),
    ("Business School", "SBS"),
    ("Law and Social Sciences", "LSS"),
    ("Education and Humanities", "EDU"),
]
TEAMS = [
    ("ENS Eagles", "ENS", "Arman Seitkali"),
    ("SBS Bulls", "SBS", "Daniyar Abenov"),
    ("LSS Lions", "LSS", "Yerlan Tokhtarov"),
    ("EDU Wolves", "EDU", "Askar Zhumabekov"),
]
FIRST = ["Aidar", "Nursultan", "Alikhan", "Dias", "Temirlan", "Sanzhar", "Miras", "Yerassyl"]
LAST = ["Nurlanov", "Bekov", "Serikov", "Omarov", "Karimov", "Akhmetov", "Sadykov", "Zhanibekov"]
POSITIONS = [Position.GOALKEEPER, Position.DEFENDER, Position.DEFENDER, Position.DEFENDER,
             Position.MIDFIELDER, Position.MIDFIELDER, Position.FORWARD, Position.FORWARD]


def seed(store) -> None:
    if store.faculties.all():
        return

    faculty_ids = {}
    for name, code in FACULTIES:
        faculty_ids[code] = faculties.create_faculty(store, FacultyCreate(name=name, code=code)).id

    team_ids = []
    for t_index, (name, code, coach) in enumerate(TEAMS):
        team = teams.create_team(store, TeamCreate(name=name, faculty_id=faculty_ids[code], coach_name=coach))
        team_ids.append(team.id)
        for p_index in range(8):
            players.add_player(store, team.id, PlayerCreate(
                first_name=FIRST[(p_index + t_index) % 8],
                last_name=LAST[(p_index + 2 * t_index) % 8],
                student_id=f"2201{t_index:02d}{p_index:03d}",
                jersey_number=[1, 2, 4, 5, 8, 6, 9, 10][p_index],
                position=POSITIONS[p_index],
            ))

    cup = tournaments.create_tournament(store, TournamentCreate(
        name="SDU Autumn Cup", season="2026/2027",
        start_date=date(2026, 11, 1), end_date=date(2026, 12, 20), max_teams=8,
    ))
    for team_id in team_ids:
        tournaments.enroll_team(store, cup.id, EnrollmentCreate(team_id=team_id))
    tournaments.start_tournament(store, cup.id)

    a, b, c, d = team_ids
    fixtures = [
        (a, b, datetime(2026, 11, 5, 15)), (c, d, datetime(2026, 11, 5, 18)),
        (a, c, datetime(2026, 11, 12, 15)), (b, d, datetime(2026, 11, 12, 18)),
        (a, d, datetime(2026, 11, 26, 15)), (b, c, datetime(2026, 11, 26, 18)),
    ]
    scheduled = [
        matches.schedule_match(store, cup.id, MatchCreate(home_team_id=h, away_team_id=aw, kickoff=k))
        for h, aw, k in fixtures
    ]

    def roster(team_id):
        return players.list_team_players(store, team_id)

    # Play the first four fixtures with some goals and cards.
    results = [
        [(EventType.GOAL, 12, a, 6, 7), (EventType.YELLOW_CARD, 30, b, 2, None), (EventType.GOAL, 55, b, 7, 6),
         (EventType.GOAL, 81, a, 7, None)],
        [(EventType.GOAL, 20, d, 6, None), (EventType.GOAL, 44, d, 7, 4)],
        [(EventType.GOAL, 9, a, 6, None), (EventType.OWN_GOAL, 60, c, 2, None)],
        [(EventType.GOAL, 33, b, 6, 5), (EventType.GOAL, 70, d, 6, None), (EventType.RED_CARD, 88, d, 3, None)],
    ]
    for match, match_events in zip(scheduled, results):
        matches.start_match(store, match.id)
        for ev_type, minute, team_id, idx, assist_idx in match_events:
            squad = roster(team_id)
            events.record_event(store, match.id, EventCreate(
                type=ev_type, minute=minute, player_id=squad[idx].id,
                assist_player_id=squad[assist_idx].id if assist_idx is not None else None,
            ))
        matches.finish_match(store, match.id)


if __name__ == "__main__":
    from app.db.session import SessionLocal
    from app.repositories.sql import SqlStore

    with SessionLocal() as session:
        store = SqlStore(session)
        if store.faculties.all():
            print("Database already has data; seed skipped.")
        else:
            seed(store)
            print("Demo data created.")
