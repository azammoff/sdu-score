"""End-to-end checks of the main workflows and their failure cases.

Seed data: 4 faculties, 4 teams (ids 1-4, 8 players each, ids 1-32), tournament 1 "ongoing"
with matches 1-4 finished and matches 5-6 scheduled on 2026-11-26.
"""

from tests.conftest import ADMIN


def new_player(student_id="230000001", jersey=77, **extra):
    return {"first_name": "Test", "last_name": "Player", "student_id": student_id,
            "jersey_number": jersey, "position": "MF", **extra}


def error_code(resp):
    return resp.json()["error"]["code"]


# ---------- auth & validation ----------

def test_write_needs_api_key(client):
    r = client.post("/faculties", json={"name": "Medicine", "code": "MED"})
    assert r.status_code == 401 and error_code(r) == "unauthorized"
    r = client.post("/faculties", json={"name": "Medicine", "code": "MED"}, headers={"X-API-Key": "wrong"})
    assert r.status_code == 401


def test_validation_errors_are_structured(client):
    r = client.post("/teams/1/players", json=new_player(student_id="abc", jersey=150), headers=ADMIN)
    assert r.status_code == 422
    fields = {d["field"] for d in r.json()["error"]["details"]}
    assert {"student_id", "jersey_number"} <= fields


def test_not_found(client):
    for url in ["/teams/999", "/players/999", "/tournaments/999", "/matches/999", "/faculties/999"]:
        r = client.get(url)
        assert r.status_code == 404 and error_code(r) == "not_found", url


# ---------- workflow 1: teams & rosters ----------

def test_faculty_team_player_crud(client):
    r = client.post("/faculties", json={"name": "Medicine", "code": "med"}, headers=ADMIN)
    assert r.status_code == 201 and r.json()["code"] == "MED"
    fid = r.json()["id"]

    r = client.post("/teams", json={"name": "MED Medics", "faculty_id": fid}, headers=ADMIN)
    assert r.status_code == 201
    tid = r.json()["id"]

    r = client.post(f"/teams/{tid}/players", json=new_player(), headers=ADMIN)
    assert r.status_code == 201
    pid = r.json()["id"]

    assert client.patch(f"/players/{pid}", json={"jersey_number": 9}, headers=ADMIN).json()["jersey_number"] == 9
    detail = client.get(f"/teams/{tid}").json()
    assert detail["faculty"]["code"] == "MED" and len(detail["players"]) == 1

    # Faculty with teams can't be deleted
    assert client.delete(f"/faculties/{fid}", headers=ADMIN).status_code == 409
    assert client.delete(f"/players/{pid}", headers=ADMIN).status_code == 204
    assert client.delete(f"/teams/{tid}", headers=ADMIN).status_code == 204
    assert client.delete(f"/faculties/{fid}", headers=ADMIN).status_code == 204
    assert client.get(f"/teams/{tid}").status_code == 404


def test_roster_rules(client):
    # duplicate jersey within a team
    r = client.post("/teams/1/players", json=new_player(jersey=10), headers=ADMIN)
    assert r.status_code == 409 and "Jersey #10" in r.json()["error"]["message"]
    # student registered twice
    r = client.post("/teams/2/players", json=new_player(student_id="220100000"), headers=ADMIN)
    assert r.status_code == 409
    # team in a non-existent faculty
    assert client.post("/teams", json={"name": "Ghosts", "faculty_id": 99}, headers=ADMIN).status_code == 404
    # duplicate team name
    assert client.post("/teams", json={"name": "ens eagles", "faculty_id": 1}, headers=ADMIN).status_code == 409


def test_roster_max_size(client):
    for i in range(17):  # 8 seeded + 17 = 25
        r = client.post("/teams/1/players", json=new_player(student_id=f"2400000{i:02d}", jersey=60 + i), headers=ADMIN)
        assert r.status_code == 201
    r = client.post("/teams/1/players", json=new_player(student_id="240000099", jersey=99), headers=ADMIN)
    assert r.status_code == 422 and error_code(r) == "business_rule_violation"


def test_cannot_delete_team_or_player_with_history(client):
    assert client.delete("/teams/1", headers=ADMIN).status_code == 409
    assert client.delete("/players/7", headers=ADMIN).status_code == 409  # scored in seed


def test_player_transfer(client):
    r = client.patch("/players/8", json={"team_id": 3}, headers=ADMIN)  # jersey 10 exists at team 3
    assert r.status_code == 409
    r = client.patch("/players/8", json={"team_id": 3, "jersey_number": 33}, headers=ADMIN)
    assert r.status_code == 200 and r.json()["team_id"] == 3


# ---------- workflow 2: tournaments & scheduling ----------

def make_tournament(client, **over):
    body = {"name": "Spring League", "season": "2027", "start_date": "2027-03-01",
            "end_date": "2027-05-31", "max_teams": 3, **over}
    return client.post("/tournaments", json=body, headers=ADMIN)


def test_tournament_lifecycle(client):
    r = make_tournament(client)
    assert r.status_code == 201 and r.json()["status"] == "upcoming"
    tid = r.json()["id"]

    assert make_tournament(client).status_code == 409  # same name + season
    assert make_tournament(client, name="Bad", end_date="2027-01-01").status_code == 422

    # can't start with fewer than 2 teams
    assert client.post(f"/tournaments/{tid}/start", headers=ADMIN).status_code == 422

    for team_id in (1, 2, 3):
        assert client.post(f"/tournaments/{tid}/teams", json={"team_id": team_id}, headers=ADMIN).status_code == 201
    r = client.post(f"/tournaments/{tid}/teams", json={"team_id": 1}, headers=ADMIN)
    assert r.status_code == 409  # already enrolled
    r = client.post(f"/tournaments/{tid}/teams", json={"team_id": 4}, headers=ADMIN)
    assert r.status_code == 409 and "full" in r.json()["error"]["message"]

    assert client.patch(f"/tournaments/{tid}", json={"max_teams": 2}, headers=ADMIN).status_code == 422
    assert client.delete(f"/tournaments/{tid}/teams/3", headers=ADMIN).status_code == 204
    assert client.post(f"/tournaments/{tid}/start", headers=ADMIN).json()["status"] == "ongoing"

    # registration closed, structural edits locked
    assert client.post(f"/tournaments/{tid}/teams", json={"team_id": 3}, headers=ADMIN).status_code == 409
    assert client.patch(f"/tournaments/{tid}", json={"max_teams": 8}, headers=ADMIN).status_code == 409
    assert client.patch(f"/tournaments/{tid}", json={"name": "Spring League 2027"}, headers=ADMIN).status_code == 200

    assert client.post(f"/tournaments/{tid}/finish", headers=ADMIN).json()["status"] == "finished"
    assert client.get("/tournaments", params={"status": "finished"}).json()[0]["id"] == tid


def test_optional_fields_for_real_world_data(client):
    # A team without a faculty and a player without student ID / jersey / position are allowed
    team = client.post("/teams", json={"name": "Old School"}, headers=ADMIN)
    assert team.status_code == 201 and team.json()["faculty_id"] is None
    tid = team.json()["id"]
    r = client.post(f"/teams/{tid}/players", json={"first_name": "Miras", "last_name": "Serik"}, headers=ADMIN)
    assert r.status_code == 201 and r.json()["jersey_number"] is None and r.json()["full_name"] == "Miras Serik"
    # two players without a jersey number don't clash
    r = client.post(f"/teams/{tid}/players", json={"first_name": "Dias", "last_name": "Omar"}, headers=ADMIN)
    assert r.status_code == 201
    # a team without players can enroll now (no minimum roster)
    tour = make_tournament(client).json()["id"]
    assert client.post(f"/tournaments/{tour}/teams", json={"team_id": tid}, headers=ADMIN).status_code == 201


def test_stages_groups_and_names(client):
    url = "/tournaments/1/matches"
    body = {"home_team_id": 1, "away_team_id": 3, "kickoff": "2026-12-01T15:00:00", "stage": "Semi-final", "group_name": "a"}
    r = client.post(url, json=body, headers=ADMIN)
    assert r.status_code == 201
    m = r.json()
    assert m["stage"] == "Semi-final" and m["group_name"] == "A" and m["home_team_name"] == "ENS Eagles"
    assert [x["id"] for x in client.get(url, params={"stage": "Semi-final"}).json()] == [m["id"]]
    assert client.get("/tournaments/1").json()["stages"] == ["Semi-final"]
    latest = client.get("/matches", params={"newest_first": True, "limit": 1}).json()
    assert len(latest) == 1 and latest[0]["id"] == m["id"]
    event = client.get("/matches/1").json()["events"][0]
    assert event["player_name"] and event["assist_player_name"]


def test_scheduling_rules(client):
    url = "/tournaments/1/matches"
    base = {"home_team_id": 1, "away_team_id": 3, "venue": "SDU Arena"}
    # team vs itself (schema validation)
    assert client.post(url, json={**base, "away_team_id": 1, "kickoff": "2026-12-01T15:00:00"}, headers=ADMIN).status_code == 422
    # outside tournament dates
    r = client.post(url, json={**base, "kickoff": "2027-01-10T15:00:00"}, headers=ADMIN)
    assert r.status_code == 422 and "between" in r.json()["error"]["message"]
    # team 1 already plays at 15:00 on 2026-11-26
    r = client.post(url, json={**base, "kickoff": "2026-11-26T16:00:00"}, headers=ADMIN)
    assert r.status_code == 409
    # team not enrolled
    other = client.post("/teams", json={"name": "Outsiders", "faculty_id": 1}, headers=ADMIN).json()
    r = client.post(url, json={**base, "away_team_id": other["id"], "kickoff": "2026-12-01T15:00:00"}, headers=ADMIN)
    assert r.status_code == 422
    # valid, then reschedule and cancel
    r = client.post(url, json={**base, "kickoff": "2026-12-01T15:00:00"}, headers=ADMIN)
    assert r.status_code == 201
    mid = r.json()["id"]
    r = client.patch(f"/matches/{mid}", json={"kickoff": "2026-12-02T12:00:00+05:00"}, headers=ADMIN)
    assert r.status_code == 200 and r.json()["kickoff"] == "2026-12-02T07:00:00"
    assert client.post(f"/matches/{mid}/cancel", headers=ADMIN).json()["status"] == "cancelled"
    assert client.patch(f"/matches/{mid}", json={"venue": "X Field"}, headers=ADMIN).status_code == 409
    assert client.delete(f"/matches/{mid}", headers=ADMIN).status_code == 204


def test_match_filters(client):
    assert len(client.get("/matches", params={"status": "finished"}).json()) == 4
    assert len(client.get("/matches", params={"team_id": 1}).json()) == 3
    r = client.get("/matches", params={"date_from": "2026-11-20T00:00:00", "tournament_id": 1})
    assert [m["id"] for m in r.json()] == [5, 6]
    assert client.get("/matches", params={"status": "nope"}).status_code == 422


# ---------- workflow 3: live results & events ----------

def test_live_match_flow(client):
    # match 5: team 1 (players 1-8) vs team 4 (players 25-32)
    assert client.post("/matches/5/events", json={"type": "goal", "minute": 5, "player_id": 7}, headers=ADMIN).status_code == 409
    assert client.post("/matches/5/start", headers=ADMIN).json()["status"] == "live"
    assert client.post("/matches/5/start", headers=ADMIN).status_code == 409

    r = client.post("/matches/5/events", json={"type": "goal", "minute": 10, "player_id": 7, "assist_player_id": 8}, headers=ADMIN)
    assert r.status_code == 201 and r.json()["score"] == {"home": 1, "away": 0}
    r = client.post("/matches/5/events", json={"type": "own_goal", "minute": 20, "player_id": 2}, headers=ADMIN)
    assert r.json()["score"] == {"home": 1, "away": 1}

    # player from a team not in this match
    r = client.post("/matches/5/events", json={"type": "goal", "minute": 25, "player_id": 10}, headers=ADMIN)
    assert r.status_code == 422
    # assist from the other team
    r = client.post("/matches/5/events", json={"type": "goal", "minute": 26, "player_id": 7, "assist_player_id": 31}, headers=ADMIN)
    assert r.status_code == 422
    # assist on a card -> schema error
    r = client.post("/matches/5/events", json={"type": "yellow_card", "minute": 26, "player_id": 7, "assist_player_id": 8}, headers=ADMIN)
    assert r.status_code == 422

    # two yellows -> automatic red, then the player is out
    first = client.post("/matches/5/events", json={"type": "yellow_card", "minute": 30, "player_id": 26}, headers=ADMIN).json()
    r = client.post("/matches/5/events", json={"type": "yellow_card", "minute": 50, "player_id": 26}, headers=ADMIN)
    second = r.json()
    assert second["auto_events"][0]["type"] == "red_card"
    r = client.post("/matches/5/events", json={"type": "goal", "minute": 60, "player_id": 26}, headers=ADMIN)
    assert r.status_code == 422 and "sent off" in r.json()["error"]["message"]

    # auto red can't be deleted directly; deleting the second yellow removes it
    auto_id = second["auto_events"][0]["id"]
    assert client.delete(f"/matches/5/events/{auto_id}", headers=ADMIN).status_code == 422
    assert client.delete(f"/matches/5/events/{second['event']['id']}", headers=ADMIN).status_code == 204
    assert client.post("/matches/5/events", json={"type": "goal", "minute": 70, "player_id": 26}, headers=ADMIN).status_code == 201
    assert first["event"]["type"] == "yellow_card"

    assert client.get("/matches/5").json()["away_score"] == 2
    assert client.delete("/matches/5/events/9999", headers=ADMIN).status_code == 404
    assert client.delete("/matches/5", headers=ADMIN).status_code == 409

    assert client.post("/matches/5/finish", headers=ADMIN).json()["status"] == "finished"
    # finished matches are locked
    assert client.post("/matches/5/events", json={"type": "goal", "minute": 90, "player_id": 7}, headers=ADMIN).status_code == 409
    assert client.delete(f"/matches/5/events/{first['event']['id']}", headers=ADMIN).status_code == 409


def test_cannot_start_match_before_tournament(client):
    tid = make_tournament(client).json()["id"]
    for team_id in (1, 2):
        client.post(f"/tournaments/{tid}/teams", json={"team_id": team_id}, headers=ADMIN)
    m = client.post(f"/tournaments/{tid}/matches",
                    json={"home_team_id": 1, "away_team_id": 2, "kickoff": "2027-03-10T15:00:00"}, headers=ADMIN).json()
    r = client.post(f"/matches/{m['id']}/start", headers=ADMIN)
    assert r.status_code == 409
    # and tournament can't finish while that match is pending
    client.post(f"/tournaments/{tid}/start", headers=ADMIN)
    assert client.post(f"/tournaments/{tid}/finish", headers=ADMIN).status_code == 409
    # played tournament can't be deleted
    assert client.delete("/tournaments/1", headers=ADMIN).status_code == 409


# ---------- workflow 4: standings & statistics ----------

def test_standings_and_stats(client):
    table = client.get("/tournaments/1/standings").json()
    assert [row["team_name"] for row in table] == ["ENS Eagles", "EDU Wolves", "SBS Bulls", "LSS Lions"]
    assert table[0]["points"] == 6 and table[0]["goal_difference"] == 3

    scorers = client.get("/tournaments/1/top-scorers", params={"limit": 2}).json()
    assert len(scorers) == 2 and scorers[0]["goals"] == 2
    assert client.get("/tournaments/1/top-scorers", params={"limit": 0}).status_code == 422

    team = client.get("/teams/1/stats", params={"tournament_id": 1}).json()
    assert team["wins"] == 2 and team["clean_sheets"] == 1

    player = client.get("/players/7/stats").json()
    assert player["goals"] == 2

    detail = client.get("/tournaments/1").json()
    assert detail["team_count"] == 4 and detail["finished_match_count"] == 4
