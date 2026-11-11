"""The Teams plugin: fixtures from a feed, availability, line-ups and
carpooling.

Runs with Hubra's fixtures once the plugin is in plugins/teams of a Hubra
checkout (see README.md).
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from tests.helpers import set_modules
from tests.settings.test_settings_kv import _login, _make_role_and_member

BASE = "/api/v1/app/teams"


@pytest.fixture
def club(client, app, db, seeded_db):
    """Kim sets up teams; Cora leads Herren 1, where Max and Lea play; Ola
    plays elsewhere."""
    from hubra.core.models.group import Group, GroupMembership

    set_modules(True, "teams")
    app.test_cli_runner().invoke(args=["sync-permissions"])
    tier = seeded_db["tier"]
    kim = _make_role_and_member(
        db, tier, name="Kim", permission_keys=["teams.teams.update"]
    )
    cora = _make_role_and_member(db, tier, name="Cora")
    max_ = _make_role_and_member(db, tier, name="Max")
    lea = _make_role_and_member(db, tier, name="Lea")
    ola = _make_role_and_member(db, tier, name="Ola")
    group = Group(name="Herren 1", type="team", lead_id=cora.id)
    db.session.add(group)
    db.session.flush()
    for m in (cora, max_, lea):
        db.session.add(GroupMembership(group_id=group.id, member_id=m.id))
    db.session.commit()
    return {
        "kim": kim.id,
        "cora": cora.id,
        "max": max_.id,
        "lea": lea.id,
        "ola": ola.id,
        "group": group.id,
    }


def _ics(
    day: date, uid: str = "m1@league", summary: str = "FC Muster - SC Gegner"
) -> str:
    stamp = day.strftime("%Y%m%d")
    return (
        "BEGIN:VCALENDAR\r\nVERSION:2.0\r\n"
        "BEGIN:VEVENT\r\n"
        f"UID:{uid}\r\n"
        f"DTSTART;TZID=Europe/Zurich:{stamp}T150000\r\n"
        f"SUMMARY:{summary}\r\n"
        "LOCATION:Sportplatz Allmend\\, Bern\r\n"
        "END:VEVENT\r\n"
        "BEGIN:VEVENT\r\n"
        "UID:m2@league\r\n"
        f"DTSTART:{(day + timedelta(days=7)).strftime('%Y%m%d')}T180000Z\r\n"
        "SUMMARY:FC Rivalen – FC Muster 2\r\n"
        "END:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )


def test_a_feed_brings_matches_into_the_team_and_the_calendar(app, client, db, club):
    from hubra.core.models.event import ClubEvent
    from hubra_teams import services
    from hubra_teams.models import TeamsMatch, TeamsTeam

    _login(client, "kim@test.ch")
    assert (
        client.post(
            f"{BASE}/teams",
            json={"groupId": club["group"], "feedUrl": "http://x.ch/a.ics"},
        ).status_code
        == 400
    )
    team = client.post(
        f"{BASE}/teams",
        json={
            "groupId": club["group"],
            "feedUrl": "webcal://league.example/team.ics",
            "feedName": "FC Muster",
        },
    ).get_json()
    assert team["feedUrl"] == "https://league.example/team.ics" and team["players"] == 3

    day = date.today() + timedelta(days=5)
    with app.test_request_context():
        t = db.session.get(TeamsTeam, team["id"])
        assert services.sync(t, _ics(day)) == {"added": 2, "updated": 0, "cancelled": 0}
        db.session.commit()
    matches = client.get(f"{BASE}/teams/{team['id']}/matches").get_json()
    assert [m["opponent"] for m in matches] == ["SC Gegner", "FC Rivalen"]
    assert matches[0]["home"] is True and matches[1]["home"] is False
    assert matches[0]["startsAt"] == f"{day.isoformat()}T15:00"
    assert matches[0]["location"] == "Sportplatz Allmend, Bern"
    event = db.session.get(
        ClubEvent, db.session.get(TeamsMatch, matches[0]["id"]).event_id
    )
    assert event.title == "Herren 1 – SC Gegner" and event.category == "competition"

    # The league moves the first match and drops the second.
    with app.test_request_context():
        t = db.session.get(TeamsTeam, team["id"])
        text = (
            _ics(day + timedelta(days=1)).split("BEGIN:VEVENT\r\nUID:m2")[0]
            + "END:VCALENDAR\r\n"
        )
        assert services.sync(t, text) == {"added": 0, "updated": 1, "cancelled": 1}
        db.session.commit()
    second = db.session.get(TeamsMatch, matches[1]["id"])
    assert second.cancelled is True and second.event_id is None

    # Only coaches add matches; Ola (not in the team) sees fixtures, not answers.
    _login(client, "max@test.ch")
    starts = f"{(date.today() + timedelta(days=2)).isoformat()}T19:30"
    assert (
        client.post(
            f"{BASE}/teams/{team['id']}/matches",
            json={"opponent": "X", "startsAt": starts},
        ).status_code
        == 403
    )
    _login(client, "cora@test.ch")
    made = client.post(
        f"{BASE}/teams/{team['id']}/matches",
        json={"opponent": "Testspiel", "startsAt": starts, "home": True},
    )
    assert made.status_code == 201
    _login(client, "ola@test.ch")
    seen = client.get(f"{BASE}/matches/{made.get_json()['id']}").get_json()
    assert seen["opponent"] == "Testspiel" and "answers" not in seen
    assert (
        client.put(
            f"{BASE}/matches/{seen['id']}/answer", json={"answer": "yes"}
        ).status_code
        == 403
    )


def test_answers_lineup_and_rides(client, db, club):
    from hubra.core.models.notification import Notification

    _login(client, "kim@test.ch")
    team = client.post(f"{BASE}/teams", json={"groupId": club["group"]}).get_json()
    _login(client, "cora@test.ch")
    starts = f"{(date.today() + timedelta(days=4)).isoformat()}T14:00"
    match = client.post(
        f"{BASE}/teams/{team['id']}/matches",
        json={"opponent": "SC Gegner", "startsAt": starts, "home": False},
    ).get_json()

    _login(client, "max@test.ch")
    assert (
        client.put(
            f"{BASE}/matches/{match['id']}/answer", json={"answer": "yes"}
        ).get_json()["counts"]["yes"]
        == 1
    )
    assert (
        client.put(
            f"{BASE}/matches/{match['id']}/answer", json={"answer": "later"}
        ).status_code
        == 400
    )
    assert (
        client.put(
            f"{BASE}/matches/{match['id']}/lineup", json={"picks": []}
        ).status_code
        == 403
    )
    _login(client, "lea@test.ch")
    client.put(
        f"{BASE}/matches/{match['id']}/answer",
        json={"answer": "maybe", "note": "bis 13 Uhr Arbeit"},
    )
    # The line-up isn't shown before it's published.
    assert "lineup" not in client.get(f"{BASE}/matches/{match['id']}").get_json()

    _login(client, "cora@test.ch")
    view = client.get(f"{BASE}/matches/{match['id']}").get_json()
    assert {a["name"] for a in view["answers"]} == {"Test Max", "Test Lea"}
    assert [u["name"] for u in view["unanswered"]] == ["Test Cora"]
    assert (
        client.put(
            f"{BASE}/matches/{match['id']}/lineup",
            json={"picks": [{"memberId": club["ola"]}]},
        ).status_code
        == 400
    )
    done = client.put(
        f"{BASE}/matches/{match['id']}/lineup",
        json={
            "picks": [
                {"memberId": club["max"], "role": "starter", "position": "Tor"},
                {"memberId": club["lea"], "role": "sub"},
            ],
            "publish": True,
        },
    ).get_json()
    assert [p["role"] for p in done["lineup"]] == ["starter", "sub"]
    told = db.session.query(Notification).filter(
        Notification.title.in_(["Du bist aufgestellt", "You're in the line-up"])
    )
    assert {n.member_id for n in told} == {club["max"], club["lea"]}

    # Cora drives with two seats; Max and Lea fill them, Ola can't ride.
    rides = client.post(
        f"{BASE}/matches/{match['id']}/rides",
        json={"seats": 2, "fromPlace": "Clubhaus", "departs": "12:45"},
    )
    assert rides.status_code == 201
    ride = rides.get_json()["rides"][0]
    _login(client, "max@test.ch")
    assert client.get(f"{BASE}/matches/{match['id']}").get_json()["picked"] is True
    client.put(f"{BASE}/rides/{ride['id']}/seat")
    _login(client, "lea@test.ch")
    after = client.put(f"{BASE}/rides/{ride['id']}/seat").get_json()
    assert {r["name"] for r in after["rides"][0]["riders"]} == {"Test Max", "Test Lea"}
    _login(client, "ola@test.ch")
    assert client.put(f"{BASE}/rides/{ride['id']}/seat").status_code == 403
    _login(client, "lea@test.ch")
    client.delete(f"{BASE}/rides/{ride['id']}/seat")
    _login(client, "max@test.ch")
    assert client.delete(f"{BASE}/rides/{ride['id']}").status_code == 403


def test_players_without_an_answer_are_reminded_once(app, client, db, club):
    from hubra.core.models.notification import Notification
    from hubra_teams import services

    _login(client, "kim@test.ch")
    team = client.post(f"{BASE}/teams", json={"groupId": club["group"]}).get_json()
    _login(client, "cora@test.ch")
    starts = f"{(date.today() + timedelta(days=2)).isoformat()}T10:00"
    match = client.post(
        f"{BASE}/teams/{team['id']}/matches",
        json={"opponent": "SC Gegner", "startsAt": starts},
    ).get_json()
    _login(client, "max@test.ch")
    client.put(f"{BASE}/matches/{match['id']}/answer", json={"answer": "no"})
    with app.test_request_context():
        assert services.remind() == 2
        assert services.remind() == 0
        db.session.commit()
    reminded = db.session.query(Notification).filter(
        Notification.link == f"/app/teams/matches/{match['id']}"
    )
    assert {n.member_id for n in reminded} == {club["cora"], club["lea"]}


# ── Dashboard widgets ───────────────────────────────────────────────────────


def test_matches_widget(db, club):
    from hubra.core import contracts
    from hubra.core.models.group import Group
    from hubra.core.models.member import Member
    from hubra_teams import services
    from hubra_teams.models import TeamsAnswer, TeamsMatch, TeamsTeam

    other = Group(name="Damen 1", type="team")
    db.session.add(other)
    db.session.flush()
    mine = TeamsTeam(group_id=club["group"])
    theirs = TeamsTeam(group_id=other.id)
    db.session.add_all([mine, theirs])
    db.session.flush()
    soon = services.local_now() + timedelta(days=2)
    first = TeamsMatch(team_id=mine.id, opponent="SC Gegner", home=True,
                       starts_at=soon, location="Halle Nord")
    db.session.add_all([
        first,
        TeamsMatch(team_id=mine.id, opponent="FC Weg", home=False,
                   starts_at=soon + timedelta(days=7)),
        TeamsMatch(team_id=mine.id, opponent="Abgesagt", starts_at=soon, cancelled=True),
        TeamsMatch(team_id=mine.id, opponent="Vorbei", starts_at=soon - timedelta(days=9)),
        TeamsMatch(team_id=theirs.id, opponent="FC Andere", starts_at=soon),
    ])
    db.session.flush()
    db.session.add(TeamsAnswer(match_id=first.id, member_id=club["max"], answer="yes"))
    db.session.commit()

    max_ = db.session.get(Member, club["max"])
    out = contracts.widget_data("teams.matches", {}, actor=max_)
    assert [i["label"] for i in out["items"]] == [
        "Herren 1 vs SC Gegner",
        "Herren 1 @ FC Weg",
    ]
    assert "Halle Nord" in out["items"][0]["sub"]
    assert out["items"][0]["sub"].endswith(("Dabei", "In"))
    assert out["items"][1]["sub"].endswith(("Noch offen", "Not answered"))
    assert out["items"][0]["path"] == f"/app/teams/matches/{first.id}"

    every = contracts.widget_data("teams.matches", {"mine": False}, actor=max_)
    assert len(every["items"]) == 3
    # Ola plays in no team: nothing of her own, and no answer on others.
    ola = db.session.get(Member, club["ola"])
    assert contracts.widget_data("teams.matches", {}, actor=ola)["items"] == []
    other_match = contracts.widget_data("teams.matches", {"mine": False}, actor=ola)
    assert not any("offen" in i["sub"] or "answered" in i["sub"] for i in other_match["items"])


def test_feed_connects_only_to_the_checked_address(monkeypatch):
    # DNS rebinding: the host looked public when the link was saved and
    # points into Hubra's own network at the fetch.
    import pytest
    from hubra_teams import feed

    monkeypatch.delenv("TEAMS_FEED_ALLOW_PRIVATE", raising=False)
    answers = iter(["93.184.215.14", "169.254.169.254"])
    monkeypatch.setattr(
        feed.socket,
        "getaddrinfo",
        lambda host, *a, **k: [(0, 0, 0, "", (next(answers), 443))],
    )
    monkeypatch.setattr(
        feed.socket,
        "create_connection",
        lambda *a, **k: pytest.fail("connected to a private address"),
    )
    with pytest.raises(feed.FeedError, match="not a public address"):
        feed.fetch("https://league.example.ch/team.ics")
