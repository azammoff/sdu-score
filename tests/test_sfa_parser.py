"""The Telegram post parser, on post formats copied from the channel (no database needed)."""

from app.importers.sfa_parser import parse_post, team_key


def post(text, id=1, date="2025-04-01T19:32:04"):
    return {"id": id, "type": "message", "date": date, "text": text}


def test_modern_format_with_team_suffix_and_assists():
    [m] = parse_post(post(
        "SFC 2026 1/2 final | 2 - leg\n\nFuria 3:3 Sunkar\n\n"
        "2’⚽️ Miras - Furia\n10’⚽️ Almat Abdimanap(Dinmukhamed Akhmadi) - Sunkar\n"
        "14’⚽️ Abilkhaiyr(Toremyrza)-Furia\n31’🟨 Sanzhar Jagparov - Sunkar\n"
    ))
    assert (m.competition, m.season, m.stage, m.leg) == ("SFC", 2026, "Semi-final", 2)
    assert (m.home, m.home_score, m.away_score, m.away) == ("Furia", 3, 3, "Sunkar")
    goal = m.events[1]
    assert (goal.type, goal.minute, goal.player, goal.assist, goal.side) == ("goal", 10, "Almat Abdimanap", "Dinmukhamed Akhmadi", "away")
    assert m.events[2].player == "Abilkhaiyr" and m.events[2].side == "home"
    assert m.events[3].type == "yellow_card" and m.events[3].side == "away"


def test_old_format_uses_running_score_and_own_goals():
    [m] = parse_post(post(
        "SFC 2021\n\n1 tour\n\nTeachers 3-2 Nacional\n1st half:\n"
        "⚽️ 2’ Нысанбаев Динмухамед(Маматкалиев Максат) 0-1\n🔶 16’ Бектурсын Дамир\n"
        "⚽️ 24’ Бектурсын Дамир 1-1\n⚽️ 30’ Сахиев Адилет(автогол) 2-1\n⚽️ 35’ Бектурсын Дамир 2-2 (Досанұлы Донай)\n"
        "⚽️ 40’ Бектурсын Дамир 3-2\n"
    ))
    assert m.stage == "Tour 1"
    sides = [(e.type, e.side) for e in m.events if e.type != "yellow_card"]
    # the own goal (2-1 for Teachers) was scored by a Nacional player
    assert sides == [("goal", "away"), ("goal", "home"), ("own_goal", "away"), ("goal", "away"), ("goal", "home")]
    assert m.events[4].assist == "Досанұлы Донай"


def test_group_line_penalties_and_missed_penalty():
    [m] = parse_post(post(
        "SFL 2025 Qualification\n\nGroup A\n\nHunters 1 : 1 Tamyr\n\n"
        "2’⚽️ Yerzhan Assylkhanov - Tamyr\n10’⚽️ Yerzat Orazzhan - Hunters\n"
        "35’❌ Sanzhar Mukimov(Penalty) - Hunters\nСерия пенальти: (3 : 2)\n"
    ))
    assert (m.stage, m.group) == ("Qualification", "A")
    assert len(m.events) == 2  # the missed penalty is not an event
    assert (m.home_penalties, m.away_penalties) == (3, 2)


def test_schedule_posts_are_ignored():
    assert parse_post(post("SFL 2023\nРасписание матчей на 28 марта:\n\n1 тур. 18:00. I One - Barabar")) == []


def test_team_key_merges_spellings():
    assert team_key("FC Snow kids") == team_key("Snow Kids")
    assert team_key("I.ONE") == team_key("I One")
    assert team_key("FC Allıance") == team_key("Alliance")
