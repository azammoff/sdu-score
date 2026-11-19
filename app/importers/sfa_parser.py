"""Parse match reports from the SDU Football Association Telegram channel export (result.json).

The channel posts results as free text, and the format changed over the years, e.g.

    SFL 2023                         SFC 2021
                                     1 tour
    Pride  4 : 1  SAQ                Teachers 3-2 Nacional
    9’🟨 Baibol Bakytzhanuly - SAQ   ⚽️ 2’ Nysanbayev (Mamatkaliyev) 0-1
    12’⚽️Baibol B.(Bekzat S.) - SAQ   🔶 16’ Bektursyn Damir

This module only turns text into plain data; app/importers/sfa_import.py writes it to the database.
"""

import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

GOAL, OWN_GOAL, YELLOW, RED = "goal", "own_goal", "yellow_card", "red_card"

SCORE_LINE = re.compile(
    r"^\s*(?P<home>[^\n\d⚽🟨🟥🔶🛑❌'’‘][^\n⚽🟨🟥🔶🛑❌]{0,40}?)\s+(?P<hs>\d{1,2})\s*[-–:]\s*(?P<as>\d{1,2})\s+"
    r"(?P<away>[^\n\d⚽🟨🟥🔶🛑❌\-–:][^\n⚽🟨🟥🔶🛑❌]{0,40}?)\s*$"
)
HEADER = re.compile(r"^\s*(?P<comp>SF[CL])\b\.?\s*(?P<year>20\d\d)?(?P<rest>.*)$", re.I)
GROUP = re.compile(r"\bgroup\s*([A-H])\b", re.I)
TOUR = re.compile(r"\b(\d{1,2})\s*[-.]?\s*(?:tour|tur|тур)\b", re.I)
LEG = re.compile(r"(\d)\s*-?\s*(?:leg|матч)", re.I)
MINUTE = re.compile(r"(\d{1,3})\s*(?:\+\s*\d+\s*)?['’‘`]")
RUNNING_SCORE = re.compile(r"(?<![\d'’])(\d{1,2})\s*[-–:]\s*(\d{1,2})(?![\d'’])")
TEAM_PENALTIES = re.compile(r"\((\d{1,2})\s*[-–:]\s*(\d{1,2})\s*пен", re.I)
PENALTY_SERIES = re.compile(r"пенальти[^\d]*\(?\s*(\d{1,2})\s*[-–:]\s*(\d{1,2})", re.I)
EVENT_MARKS = "⚽🟨🟥🔶🟧🛑🔴❌"
OWN_GOAL_WORDS = re.compile(r"(?<!\w)(og|оg|ог|own\s*goal|автогол|аг|а\.г\.?)(?!\w)", re.I)
NOT_ASSIST = re.compile(r"^(og|оg|ог|own\s*goal|автогол|аг|а\.г\.?|penalty|пенальти|пен|var|p|pen)$", re.I)


@dataclass
class ParsedEvent:
    type: str
    minute: int | None
    player: str
    assist: str | None = None
    team: str | None = None  # team name written in the post, if any
    running_score: tuple[int, int] | None = None
    side: str | None = None  # "home" / "away" once resolved


@dataclass
class ParsedMatch:
    competition: str  # SFC (cup) or SFL (league)
    season: int
    stage: str | None
    group: str | None
    leg: int | None
    home: str
    away: str
    home_score: int
    away_score: int
    played_at: datetime
    post_id: int
    home_penalties: int | None = None
    away_penalties: int | None = None
    events: list[ParsedEvent] = field(default_factory=list)


# ---------------------------------------------------------------- helpers


def message_text(message: dict) -> str:
    text = message.get("text", "")
    if isinstance(text, str):
        return text
    return "".join(part if isinstance(part, str) else part.get("text", "") for part in text)


def team_key(name: str) -> str:
    """Key used to match different spellings of one team: 'FC Snow kids' == 'Snow Kids'."""
    name = unicodedata.normalize("NFKD", name).replace("ı", "i").casefold()
    name = re.sub(r"\bfc\b|\bф\.?к\.?\b", "", name)
    return re.sub(r"[^\w]", "", name)


def clean(text: str) -> str:
    text = re.sub(f"[{EVENT_MARKS}️]", " ", text)
    return re.sub(r"\s+", " ", text).strip(" -–|.,")


def _stage_from(text: str) -> str | None:
    t = text.lower()
    if "super cup" in t or "суперкубок" in t:
        return "Super Cup"
    if "opening" in t or "открыти" in t or "open match" in t:
        return "Opening match"
    if "3rd place" in t or "3-место" in t or "3 место" in t or "за 3" in t:
        return "3rd place"
    if "1/8" in t:
        return "Round of 16"
    if "1/4" in t:
        return "Quarter-final"
    if "1/2" in t or "semi" in t:
        return "Semi-final"
    if re.search(r"\bfinal\b|финал", t):
        return "Final"
    if "qualif" in t or "квалиф" in t:
        return "Qualification"
    if "play-off" in t or "playoff" in t or "плей" in t:
        return "Play-off"
    return None


def _event_type(line: str) -> str | None:
    if "❌" in line:
        return None  # missed penalty: not an event we store
    if "⚽" in line:
        return OWN_GOAL if OWN_GOAL_WORDS.search(line) else GOAL
    if any(mark in line for mark in "🟥🛑🔴"):
        return RED
    if any(mark in line for mark in "🟨🔶🟧"):
        return YELLOW
    return None


def parse_event(line: str, home: str, away: str) -> ParsedEvent | None:
    kind = _event_type(line)
    if kind is None:
        return None
    body = line
    minute = None
    if m := MINUTE.search(body):
        minute = int(m.group(1))
        body = body[: m.start()] + " " + body[m.end():]
    running = None
    if m := RUNNING_SCORE.search(body):
        running = (int(m.group(1)), int(m.group(2)))
        body = body[: m.start()] + " " + body[m.end():]
    body = re.sub(r"\((?:пенальти|penalty|pen|var)\)", " ", body, flags=re.I)

    team = None
    keys = {team_key(home): home, team_key(away): away}
    # "Name(Assist) - Team" / "Name -Team"
    if m := re.search(r"\s*[-–]\s*([^\-–()]+?)\s*$", clean(body) if "(" not in body.split("-")[-1] else body):
        candidate = m.group(1)
        if team_key(candidate) in keys:
            team = keys[team_key(candidate)]
            body = clean(body)[: clean(body).rfind(candidate)]
    parens = re.findall(r"\(([^()]*)\)", body)
    assist = None
    for p in parens:
        p_clean = clean(p)
        if not p_clean or NOT_ASSIST.match(p_clean) or OWN_GOAL_WORDS.fullmatch(p_clean):
            continue
        if team_key(p_clean) in keys:
            team = team or keys[team_key(p_clean)]
        elif kind == GOAL and assist is None:
            assist = p_clean
    player = clean(re.sub(r"\([^()]*\)", " ", body))
    player = OWN_GOAL_WORDS.sub(" ", player)
    player = re.sub(r"[()\[\]]", " ", player)
    player = re.sub(r"\s+", " ", player).strip(" -–.,")
    if not player or len(player) > 60:
        return None
    return ParsedEvent(kind, minute if minute and 1 <= minute <= 130 else None, player, assist, team, running)


def resolve_sides(match: ParsedMatch) -> None:
    """Work out which team each event belongs to (for goals: the team that scored)."""
    previous = (0, 0)
    for ev in match.events:
        if ev.team:
            player_side = "home" if team_key(ev.team) == team_key(match.home) else "away"
            ev.side = player_side
        if ev.type in (GOAL, OWN_GOAL) and ev.running_score:
            h, a = ev.running_score
            if (h, a) == (previous[0] + 1, previous[1]):
                scoring_side = "home"
            elif (h, a) == (previous[0], previous[1] + 1):
                scoring_side = "away"
            else:
                scoring_side = None
            previous = (h, a)
            if scoring_side:
                # store the player's team: for an own goal that is the other side
                if ev.type == GOAL:
                    ev.side = scoring_side
                else:
                    ev.side = "away" if scoring_side == "home" else "home"
    fill_remaining_goals(match)


def fill_remaining_goals(match: ParsedMatch) -> None:
    """If the unattributed goals can only belong to one team (given the final score), assign them."""
    home = sum(1 for e in match.events if (e.type == GOAL and e.side == "home") or (e.type == OWN_GOAL and e.side == "away"))
    away = sum(1 for e in match.events if (e.type == GOAL and e.side == "away") or (e.type == OWN_GOAL and e.side == "home"))
    open_goals = [e for e in match.events if e.side is None and e.type == GOAL]
    need_home, need_away = match.home_score - home, match.away_score - away
    if open_goals and need_home == len(open_goals) and need_away == 0:
        for e in open_goals:
            e.side = "home"
    elif open_goals and need_away == len(open_goals) and need_home == 0:
        for e in open_goals:
            e.side = "away"


def player_key(name: str) -> str:
    """'Шахмар Сарсенбай' and 'Сарсенбай Шахмар' are the same person."""
    return " ".join(sorted(team_key(part) for part in name.split() if team_key(part)))


def resolve_with_known_players(matches: list["ParsedMatch"]) -> None:
    """Second pass: a player whose team is known from other matches of the season belongs to that team."""
    known: dict[tuple[str, int, str], set[str]] = {}
    for m in matches:
        for e in m.events:
            if e.side:
                own_side = e.side
                team = m.home if own_side == "home" else m.away
                known.setdefault((m.competition, m.season, player_key(e.player)), set()).add(team_key(team))
    for m in matches:
        sides = {team_key(m.home): "home", team_key(m.away): "away"}
        for e in m.events:
            if e.side is None:
                teams = known.get((m.competition, m.season, player_key(e.player)), set()) & set(sides)
                if len(teams) == 1:
                    e.side = sides[teams.pop()]
        fill_remaining_goals(m)


def goals_match_score(match: ParsedMatch) -> bool:
    home = sum(1 for e in match.events if (e.type == GOAL and e.side == "home") or (e.type == OWN_GOAL and e.side == "away"))
    away = sum(1 for e in match.events if (e.type == GOAL and e.side == "away") or (e.type == OWN_GOAL and e.side == "home"))
    return (home, away) == (match.home_score, match.away_score)


# ---------------------------------------------------------------- main entry


def parse_post(message: dict) -> list[ParsedMatch]:
    text = message_text(message)
    if "расписание" in text.lower() or not text.strip():
        return []
    lines = text.split("\n")
    first = next((l for l in lines if l.strip()), "")
    header = HEADER.match(first)
    if not header and not ("⚽" in text):
        return []
    posted = datetime.fromisoformat(message["date"])
    competition = header.group("comp").upper() if header else None
    season = int(header.group("year")) if header and header.group("year") else posted.year
    if competition is None:
        lowered = text.lower()
        competition = "SFL" if "sfl" in lowered or "league" in lowered else "SFC" if "sfc" in lowered or "cup" in lowered else None
    if competition is None:
        return []

    stage = _stage_from(header.group("rest")) if header else None
    group = None
    tour = None
    leg = None
    if header:
        if m := TOUR.search(header.group("rest")):
            tour = int(m.group(1))
        if m := LEG.search(header.group("rest")):
            leg = int(m.group(1))
        if m := GROUP.search(header.group("rest")):
            group = m.group(1).upper()

    matches: list[ParsedMatch] = []
    current: ParsedMatch | None = None
    for raw in lines[1:]:
        line = raw.strip()
        if not line:
            continue
        if any(mark in line for mark in EVENT_MARKS):
            if current and (ev := parse_event(line, current.home, current.away)):
                current.events.append(ev)
            continue
        if m := PENALTY_SERIES.search(line):
            if current:
                current.home_penalties, current.away_penalties = int(m.group(1)), int(m.group(2))
            continue
        if m := SCORE_LINE.match(line):
            home_raw, away_raw = m.group("home"), m.group("away")
            pens = {}
            for side, raw in (("home", home_raw), ("away", away_raw)):
                if p := TEAM_PENALTIES.search(raw):
                    pens = {"home_penalties": int(p.group(1)), "away_penalties": int(p.group(2))}
            # "(4) Turan" / "Nomad (4)" carry aggregate scores, "(1-2 пен.)" a shoot-out: not part of the name
            home, away = (clean(re.sub(r"\([^)]*\)", " ", raw)) for raw in (home_raw, away_raw))
            if not home or not away or team_key(home) == team_key(away) or ":" in away:
                continue
            current = ParsedMatch(
                competition=competition,
                season=season,
                stage=stage or (f"Tour {tour}" if tour else None),
                group=group,
                leg=leg,
                home=home,
                away=away,
                home_score=int(m.group("hs")),
                away_score=int(m.group("as")),
                played_at=posted,
                post_id=message["id"],
                **pens,
            )
            matches.append(current)
            continue
        # context lines between results
        if m := GROUP.search(line):
            group = m.group(1).upper()
        if m := TOUR.search(line):
            tour = int(m.group(1))
            stage = stage if stage and not stage.startswith("Tour") and stage != "Qualification" else stage
        if (s := _stage_from(line)) and len(line) < 40:
            stage = s
        if m := LEG.search(line):
            leg = int(m.group(1))

    for match in matches:
        resolve_sides(match)
    return matches


def parse_export(path: str | Path) -> list[ParsedMatch]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    matches: list[ParsedMatch] = []
    for message in data.get("messages", []):
        if message.get("type") == "message":
            matches.extend(parse_post(message))
    resolve_with_known_players(matches)
    return matches
