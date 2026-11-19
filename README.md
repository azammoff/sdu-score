# SDU Score API

**SDU Score** — a SofaScore-style site for SDU student football: the SDU Football Cup (SFC) and
SDU Football League (SFL) from 2021 to today, with results, match timelines, league and group tables,
top scorers, team and player pages. It is a FastAPI REST API plus a plain HTML/CSS/JS website.

The match history (≈800 matches, 4 000+ goals and cards) is imported from the
SDU Football Association Telegram channel export in `data/sfa_channel.json`.

Built with FastAPI, Pydantic, SQLAlchemy 2, Alembic and PostgreSQL.

> Assignment 5 (in-memory version) is tagged `a5-in-memory`; `git checkout a5-in-memory` to see it.
> The current version (Assignment 6) stores everything in PostgreSQL, so data survives restarts.

## Run

Needs Python 3.11+ and Docker (for PostgreSQL).

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

docker compose up -d          # PostgreSQL 16 on localhost:5432
alembic upgrade head          # create the tables
python -m app.importers.sfa_import data/sfa_channel.json --reset   # real match history
uvicorn app.main:app --reload
```

Website: http://127.0.0.1:8000/ · API docs: http://127.0.0.1:8000/docs

No Docker on macOS? `scripts/dev_db.sh` starts a local PostgreSQL 16 on the same port with the same
user and databases (`scripts/dev_db.sh stop` to stop it). Or point `DATABASE_URL` in `.env` at any PostgreSQL you have.

Open http://127.0.0.1:8000/docs. Read endpoints are public. For write endpoints click **Authorize**
and enter the admin key (`sdu-admin-key` by default, `ADMIN_API_KEY` in `.env`).

Instead of the real history you can load small demo data with `python -m app.seed` (only into an empty database): 4 faculties, 4 teams with 8 players each, and the
"SDU Autumn Cup" tournament (ongoing, 4 matches played, 2 scheduled for 2026-11-26).

Run the automated checks with `pytest`. They use `TEST_DATABASE_URL` (a separate database that
docker compose creates for you) and are skipped if it isn't set.

## Database

```
faculties    id PK, name UNIQUE, code UNIQUE
teams        id PK, name UNIQUE, faculty_id FK→faculties (RESTRICT), coach_name
players      id PK, team_id FK→teams (CASCADE), student_id UNIQUE, jersey_number CHECK 1–99,
             position enum, UNIQUE(team_id, jersey_number)
tournaments  id PK, name, season, start_date, end_date CHECK ≥ start_date, max_teams CHECK 2–32,
             status enum, UNIQUE(name, season)
enrollments  id PK, tournament_id FK (CASCADE), team_id FK (CASCADE), UNIQUE(tournament_id, team_id)
matches      id PK, tournament_id FK (CASCADE), home_team_id / away_team_id FK→teams (RESTRICT),
             CHECK home ≠ away, kickoff, venue, status enum, home_score, away_score
match_events id PK, match_id FK (CASCADE), player_id / assist_player_id FK→players (RESTRICT),
             team_id FK→teams, type enum, minute CHECK 1–130, is_auto
```

One-to-many: faculty → teams, team → players, tournament → matches, match → events.
Many-to-many: tournaments ↔ teams through `enrollments`.

The services check every rule first and return a clear error; the database constraints are a second
line of defence (a constraint violation is returned as 409 instead of a crash).

Migrations live in `alembic/versions/`. Useful commands:

```bash
alembic upgrade head                       # apply
alembic downgrade base                     # drop everything
alembic revision --autogenerate -m "..."   # after changing app/db/models.py
```

## Project structure

```
app/
  main.py           app setup, routers, error handlers, demo seed on startup
  config.py         settings from environment / .env
  deps.py           admin API-key check, storage dependency (one DB session per request)
  errors.py         domain errors -> JSON {"error": {code, message, details}}
  enums.py          positions, tournament/match statuses, event types
  schemas/          Pydantic request/response models (validation)
  services/         business logic (all rules live here)
  db/               SQLAlchemy base, models (tables + relationships), engine and session
  repositories/     Store/Table interface and its SQLAlchemy implementation
  routers/          thin HTTP handlers grouped by resource
  importers/        Telegram channel parser (sfa_parser.py) and database import (sfa_import.py)
  static/           the website: index.html, app.css, app.js (served at /)
  seed.py           demo data, created through the services (python -m app.seed)
alembic/            migration environment and versions
data/               Telegram channel export used for the import
scripts/dev_db.sh   PostgreSQL without Docker (macOS)
docker-compose.yml  PostgreSQL for development and tests
tests/              end-to-end API tests against PostgreSQL
```

Routers only parse the request and call a service. Services hold every business rule and talk to
storage through a small `Store`/`Table` interface, so the storage can be swapped without touching them.

## Importing the Telegram channel

```bash
python -m app.importers.sfa_import data/sfa_channel.json --reset
```

`--reset` deletes all existing data first. To refresh with a newer export, export the channel from
Telegram Desktop as JSON and import the new `result.json` the same way.

The parser (`app/importers/sfa_parser.py`) reads the free-text match posts, which changed format over the years:
competition and season from the first line (`SFC 2024`, `SFL 2025 Qualification`), stage, group, tour and leg,
the score line, and each event line (⚽ goal with assist in brackets, OG/автогол, 🟨/🔶 yellow, 🟥/🛑 red, ❌ missed
penalty is ignored, penalty shoot-outs). It decides which team an event belongs to from the team name in the
line, from the running score (`1-2`), or from the same player's other matches in that season.
About 4% of events (mostly 2021–22 posts that name no team) can't be assigned and are skipped; the match score
always comes from the result line. Different spellings of a team (`Snow kids` / `FC Snow Kids`) are merged.

Imported matches are written straight to the database as finished; the live-match rules apply to matches
recorded through the API.

## Website

`app/static/` — no build step, served by FastAPI at `/`, uses the same REST API:
home (latest results, all-time top scorers, champions), tournament (matches by stage, league/group tables with
form, top scorers), match (score, timeline, head-to-head), team and player pages, search.

## Data model

```
Faculty 1──* Team 1──* Player          (faculty is optional)
Tournament *──* Team        (Enrollment)
Tournament 1──* Match       (home team, away team)
Match 1──* MatchEvent       (goal, own goal, yellow card, red card; scorer, optional assist)
```

## Workflows and business rules

**1. Teams & rosters** — `/faculties`, `/teams`, `/teams/{id}/players`, `/players/{id}`
- Unique faculty name and code; unique team name; a team must belong to an existing faculty.
- Jersey numbers 1–99, unique within a team; a student (9-digit ID) can be registered only once.
- Roster limit of 25 players.
- Transfers (`PATCH /players/{id}` with `team_id`) are blocked while either team plays a live match.
- A faculty with teams, a team with matches, or a player with match events cannot be deleted (409).

**2. Tournaments & scheduling** — `/tournaments`, `/tournaments/{id}/teams`, `/tournaments/{id}/matches`, `/matches/{id}`
- Status flow: `upcoming` → `ongoing` (`POST /start`, needs ≥ 2 teams) → `finished` (`POST /finish`, no pending matches).
- Teams enroll only while `upcoming`, up to `max_teams`, and need at least 7 players.
- Dates, season and `max_teams` can only change while `upcoming`; `max_teams` can't drop below the enrolled count.
- Matches: a team can't play itself, both teams must be enrolled, kickoff must be within the tournament dates,
  and a team can't have two matches less than 2 hours apart.
- Only scheduled matches can be rescheduled (`PATCH`) or cancelled; live or finished matches can't be deleted.

**3. Live results & match events** — `/matches/{id}/start|finish|cancel`, `/matches/{id}/events`
- Events are recorded only while the match is `live`, and only for players of the two teams.
- The score is calculated from goal events (an own goal counts for the opponent).
- An assist must come from a teammate and is only allowed on goals.
- A second yellow card automatically adds a red card; a sent-off player can't take part any more.
- Wrong events can be deleted during the match (deleting the second yellow also removes its red card).
  Finished matches are locked.

**4. Standings & statistics**
- `GET /tournaments/{id}/standings` — 3 points for a win, 1 for a draw; ties broken by goal difference, then goals scored.
- `GET /tournaments/{id}/top-scorers?limit=10`
- `GET /teams/{id}/stats?tournament_id=` and `GET /players/{id}/stats?tournament_id=`
- Filters: `GET /matches?tournament_id=&team_id=&status=&date_from=&date_to=`, `GET /players?team_id=&position=&search=`, …

## Status codes

| Code | When |
|------|------|
| 200 / 201 / 204 | success (read or update / created / deleted) |
| 401 | missing or wrong `X-API-Key` on a write endpoint |
| 404 | resource does not exist |
| 409 | conflicting operation (duplicate, wrong status, has dependent data, DB constraint) |
| 422 | invalid input or a broken business rule |

## Try it in Swagger

1. `GET /tournaments/1/standings` — league table from seed data.
2. `POST /matches/5/start`, then `POST /matches/5/events` with `{"type": "goal", "minute": 10, "player_id": 7}` — score updates.
3. Same endpoint with `player_id: 10` → 422 (player isn't in this match).
4. `POST /matches/5/finish`, then try another event → 409 (match is locked).
5. `POST /teams/1/players` with jersey 10 → 409 (number taken).
