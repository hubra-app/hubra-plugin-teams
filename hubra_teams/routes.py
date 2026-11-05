"""Teams API: /api/v1/app/teams.

GET    /options                       what the caller may do, groups to pick
GET    /teams                         every team, the caller's first, with the next match
POST   /teams                         {groupId, feedUrl?, feedName?, homeLocation?, inCalendar?}
PATCH  /teams/<id>                    same fields
DELETE /teams/<id>                    the team and its matches (not the group)
POST   /teams/<id>/sync               read the fixture feed now (coach)
GET    /teams/<id>/matches?past=1     upcoming (or past) matches with the caller's answer
POST   /teams/<id>/matches            {opponent, startsAt, home?, meetAt?, location?, competition?, notes?}
GET    /matches/<id>                  one match: answers, line-up and rides for the team
PATCH  /matches/<id>                  same fields, plus cancelled, scoreUs, scoreThem
DELETE /matches/<id>
PUT    /matches/<id>/answer           {answer: yes|maybe|no, note?, memberId? (coach)}
PUT    /matches/<id>/lineup           {picks: [{memberId, role, position?}], publish?}
POST   /matches/<id>/rides            {seats, fromPlace?, departs?, note?}
DELETE /rides/<id>                    the driver or a coach
PUT    /rides/<id>/seat               take a seat
DELETE /rides/<id>/seat               give it back
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, request
from sqlalchemy import func, select

from hubra.core.auth.helpers import get_current_member
from hubra.core.errors import api_error
from hubra.core.extensions import db
from hubra.core.models.group import Group
from hubra.core.permissions import permission_required, require_member
from hubra.core.utils import log_audit

from . import feed, services
from .body import Invalid, _body, _bool, _can, _get, _int, _iso, _names, _text
from .models import (
    TeamsAnswer,
    TeamsMatch,
    TeamsPick,
    TeamsRide,
    TeamsSeat,
    TeamsTeam,
)
from .notify import notify

teams_bp = Blueprint("teams_bp", __name__)

ANSWERS = ("yes", "maybe", "no")
ROLES = ("starter", "sub")


# Coaching routes register teams.matches.update; a group's lead passes for
# their own team.
COACH = ("matches", "update", "Coach every team")


def _coach_team(member, team_id=None, **_kw):
    t = db.session.get(TeamsTeam, team_id) if team_id else None
    if t is not None and (services.is_coach(member, t) or _can(member, services.TEAMS)):
        return "coach"
    return None


def _coach_match(member, match_id=None, **_kw):
    m = db.session.get(TeamsMatch, match_id) if match_id else None
    return _coach_team(member, team_id=m.team_id) if m is not None else None


@teams_bp.errorhandler(Invalid)
def _invalid(exc: Invalid):
    return api_error("VALIDATION_ERROR", exc.message, 400)


def _when(data, key: str, required: bool = False) -> datetime | None:
    value = data.get(key)
    if not value:
        if required:
            raise Invalid(f"{key} is required")
        return None
    if not isinstance(value, str):
        raise Invalid(f"{key} must be a time (YYYY-MM-DDTHH:MM)")
    try:
        moment = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        raise Invalid(f"{key} must be a time (YYYY-MM-DDTHH:MM)") from None
    if moment.tzinfo is not None:
        moment = moment.astimezone(services.zone()).replace(tzinfo=None)
    return moment.replace(second=0, microsecond=0)


def _stamp(value: datetime | None) -> str | None:
    return value.isoformat(timespec="minutes") if value else None


# ── Output ───────────────────────────────────────────────────────────────────


def _team(t: TeamsTeam, groups: dict, member, manage: bool, nexts: dict) -> dict:
    g = groups.get(t.group_id)
    coach = services.is_coach(member, t)
    out = {
        "id": t.id,
        "groupId": t.group_id,
        "name": g.name if g else "?",
        "color": g.color if g else None,
        "players": len(services.players(t)),
        "mine": services.in_team(member, t),
        "coach": coach,
        "homeLocation": t.home_location,
        "inCalendar": t.in_calendar,
        "hasFeed": bool(t.feed_url),
        "next": nexts.get(t.id),
    }
    if coach or manage:
        out.update(
            {
                "feedUrl": t.feed_url,
                "feedName": t.feed_name,
                "feedSyncedAt": _iso(t.feed_synced_at),
                "feedError": t.feed_error,
            }
        )
    return out


def _counts(match_ids) -> dict[int, dict[str, int]]:
    out: dict[int, dict[str, int]] = {}
    ids = list(match_ids)
    if not ids:
        return out
    for match_id, answer, n in db.session.execute(
        select(TeamsAnswer.match_id, TeamsAnswer.answer, func.count())
        .where(TeamsAnswer.match_id.in_(ids))
        .group_by(TeamsAnswer.match_id, TeamsAnswer.answer)
    ):
        out.setdefault(match_id, {"yes": 0, "maybe": 0, "no": 0})[answer] = n
    return out


def _match(m: TeamsMatch, counts: dict, mine: dict, picked: set) -> dict:
    return {
        "id": m.id,
        "teamId": m.team_id,
        "opponent": m.opponent,
        "home": m.home,
        "startsAt": _stamp(m.starts_at),
        "meetAt": _stamp(m.meet_at),
        "location": m.location,
        "competition": m.competition,
        "notes": m.notes,
        "cancelled": m.cancelled,
        "scoreUs": m.score_us,
        "scoreThem": m.score_them,
        "fromFeed": bool(m.feed_uid),
        "lineupPublished": m.lineup_published_at is not None,
        "counts": counts.get(m.id, {"yes": 0, "maybe": 0, "no": 0}),
        "myAnswer": mine.get(m.id),
        "picked": m.id in picked,
    }


def _next_matches(team_ids, member) -> dict[int, dict]:
    now = services.local_now()
    out: dict[int, dict] = {}
    rows = db.session.scalars(
        select(TeamsMatch)
        .where(TeamsMatch.team_id.in_(list(team_ids) or [0]))
        .where(TeamsMatch.starts_at >= now - timedelta(hours=3))
        .where(TeamsMatch.cancelled.is_(False))
        .order_by(TeamsMatch.starts_at)
    )
    for m in rows:
        out.setdefault(m.team_id, m)
    return _with_mine(list(out.values()), member, by_team=True)


def _with_mine(rows: list[TeamsMatch], member, by_team: bool = False):
    ids = [m.id for m in rows]
    counts = _counts(ids)
    mine = {
        a.match_id: a.answer
        for a in db.session.scalars(
            select(TeamsAnswer)
            .where(TeamsAnswer.match_id.in_(ids or [0]))
            .where(TeamsAnswer.member_id == member.id)
        )
    }
    picked = set(
        db.session.scalars(
            select(TeamsPick.match_id)
            .join(TeamsMatch, TeamsMatch.id == TeamsPick.match_id)
            .where(TeamsPick.match_id.in_(ids or [0]))
            .where(TeamsPick.member_id == member.id)
            .where(TeamsMatch.lineup_published_at.is_not(None))
        )
    )
    out = [_match(m, counts, mine, picked) for m in rows]
    if by_team:
        return {m["teamId"]: m for m in out}
    return out


def _groups(ids) -> dict[int, Group]:
    return {
        g.id: g
        for g in db.session.scalars(select(Group).where(Group.id.in_(list(ids) or [0])))
    }


# ── Options and teams ────────────────────────────────────────────────────────


@teams_bp.get("/options")
@require_member
def options():
    member = get_current_member()
    can = {
        "teams": _can(member, services.TEAMS),
        "matches": _can(member, services.MATCHES),
    }
    out = {"can": can, "memberId": member.id}
    if can["teams"]:
        taken = set(db.session.scalars(select(TeamsTeam.group_id)))
        out["groups"] = [
            {"id": g.id, "name": g.name, "type": g.type}
            for g in db.session.scalars(select(Group).order_by(Group.name))
            if g.id not in taken
        ]
    return jsonify(out)


@teams_bp.get("/teams")
@require_member
def list_teams():
    member = get_current_member()
    manage = _can(member, services.TEAMS)
    rows = list(db.session.scalars(select(TeamsTeam)))
    groups = _groups(t.group_id for t in rows)
    nexts = _next_matches([t.id for t in rows], member)
    out = [_team(t, groups, member, manage, nexts) for t in rows]
    out.sort(key=lambda t: (not (t["mine"] or t["coach"]), t["name"].lower()))
    return jsonify(out)


def _team_fields(t: TeamsTeam, data: dict, creating: bool) -> None:
    if "feedUrl" in data or creating:
        url = _text(data, "feedUrl", 500)
        try:
            t.feed_url = feed.normalise(url) if url else None
        except feed.FeedError as exc:
            raise Invalid(str(exc)) from None
    if "feedName" in data or creating:
        t.feed_name = _text(data, "feedName", 120)
    if "homeLocation" in data or creating:
        t.home_location = _text(data, "homeLocation", 200)
    if "inCalendar" in data:
        t.in_calendar = _bool(data, "inCalendar")


@teams_bp.post("/teams")
@permission_required("teams", "update", "Set up teams and their fixture feeds")
def create_team():
    member = get_current_member()
    data = _body()
    group_id = _int(data, "groupId", 1, 2**31 - 1)
    if group_id is None or db.session.get(Group, group_id) is None:
        raise Invalid("groupId: no such group")
    if db.session.scalar(select(TeamsTeam.id).where(TeamsTeam.group_id == group_id)):
        return api_error("TEAM_EXISTS", "this group is already a team", 409)
    t = TeamsTeam(group_id=group_id, in_calendar=True)
    _team_fields(t, data, creating=True)
    db.session.add(t)
    db.session.flush()
    log_audit(member.id, "teams.team.create", "TeamsTeam", t.id, services.team_name(t))
    db.session.commit()
    return jsonify(_team(t, _groups([group_id]), member, True, {})), 201


def _coached(team_id: int):
    """The team, if the caller coaches it (or runs teams)."""
    member = get_current_member()
    t, err = _get(TeamsTeam, team_id)
    if err:
        return None, err
    if not (services.is_coach(member, t) or _can(member, services.TEAMS)):
        return None, api_error("FORBIDDEN", "only the team's coaches", 403)
    return t, None


@teams_bp.patch("/teams/<int:team_id>")
@permission_required(*COACH, allow=_coach_team)
def update_team(team_id: int):
    member = get_current_member()
    t, err = _coached(team_id)
    if err:
        return err
    data = _body()
    calendar_before = t.in_calendar
    _team_fields(t, data, creating=False)
    if t.in_calendar != calendar_before:
        for m in db.session.scalars(
            select(TeamsMatch)
            .where(TeamsMatch.team_id == t.id)
            .where(TeamsMatch.starts_at >= services.local_now())
        ):
            services.mirror(m, t)
    log_audit(member.id, "teams.team.update", "TeamsTeam", t.id, services.team_name(t))
    db.session.commit()
    nexts = _next_matches([t.id], member)
    return jsonify(
        _team(t, _groups([t.group_id]), member, _can(member, services.TEAMS), nexts)
    )


@teams_bp.delete("/teams/<int:team_id>")
@permission_required("teams", "update", "Set up teams and their fixture feeds")
def delete_team(team_id: int):
    member = get_current_member()
    t, err = _get(TeamsTeam, team_id)
    if err:
        return err
    for m in db.session.scalars(select(TeamsMatch).where(TeamsMatch.team_id == t.id)):
        services.drop_event(m)
    log_audit(member.id, "teams.team.delete", "TeamsTeam", t.id, services.team_name(t))
    db.session.delete(t)
    db.session.commit()
    return "", 204


@teams_bp.post("/teams/<int:team_id>/sync")
@permission_required(*COACH, allow=_coach_team)
def sync_team(team_id: int):
    t, err = _coached(team_id)
    if err:
        return err
    try:
        done = services.sync(t)
    except feed.FeedError as exc:
        db.session.rollback()
        t = db.session.get(TeamsTeam, team_id)
        t.feed_error = str(exc)[:300]
        db.session.commit()
        return api_error("FEED_ERROR", str(exc), 422)
    db.session.commit()
    return jsonify(done)


# ── Matches ──────────────────────────────────────────────────────────────────


@teams_bp.get("/teams/<int:team_id>/matches")
@require_member
def list_matches(team_id: int):
    member = get_current_member()
    t, err = _get(TeamsTeam, team_id)
    if err:
        return err
    now = services.local_now() - timedelta(hours=3)
    query = select(TeamsMatch).where(TeamsMatch.team_id == t.id)
    if request.args.get("past"):
        query = query.where(TeamsMatch.starts_at < now).order_by(
            TeamsMatch.starts_at.desc()
        )
    else:
        query = query.where(TeamsMatch.starts_at >= now).order_by(TeamsMatch.starts_at)
    rows = list(db.session.scalars(query.limit(200)))
    return jsonify(_with_mine(rows, member))


def _match_fields(m: TeamsMatch, data: dict, creating: bool) -> None:
    if creating or "opponent" in data:
        m.opponent = _text(data, "opponent", 200, required=True)
    if creating or "startsAt" in data:
        m.starts_at = _when(data, "startsAt", required=True)
    if creating or "meetAt" in data:
        m.meet_at = _when(data, "meetAt")
    if "home" in data or creating:
        value = data.get("home")
        m.home = None if value is None else _bool(data, "home")
    for key, attr, limit in (
        ("location", "location", 300),
        ("competition", "competition", 120),
        ("notes", "notes", 5000),
    ):
        if creating or key in data:
            setattr(m, attr, _text(data, key, limit))
    if "cancelled" in data:
        m.cancelled = _bool(data, "cancelled")
    if "scoreUs" in data:
        m.score_us = _int(data, "scoreUs", 0, 999)
    if "scoreThem" in data:
        m.score_them = _int(data, "scoreThem", 0, 999)


@teams_bp.post("/teams/<int:team_id>/matches")
@permission_required(*COACH, allow=_coach_team)
def create_match(team_id: int):
    member = get_current_member()
    t, err = _coached(team_id)
    if err:
        return err
    m = TeamsMatch(team_id=t.id, cancelled=False)
    data = _body()
    _match_fields(m, data, creating=True)
    if m.home and not m.location:
        m.location = t.home_location
    db.session.add(m)
    db.session.flush()
    services.mirror(m, t)
    log_audit(member.id, "teams.match.create", "TeamsMatch", m.id, m.opponent)
    db.session.commit()
    return jsonify(_with_mine([m], member)[0]), 201


def _visible_match(match_id: int):
    """The match and its team, and whether the caller belongs to it."""
    member = get_current_member()
    m, err = _get(TeamsMatch, match_id)
    if err:
        return None, None, None, err
    t = db.session.get(TeamsTeam, m.team_id)
    coach = services.is_coach(member, t)
    inside = coach or services.in_team(member, t)
    return m, t, {"coach": coach, "inside": inside}, None


@teams_bp.get("/matches/<int:match_id>")
@require_member
def get_match(match_id: int):
    member = get_current_member()
    m, t, who, err = _visible_match(match_id)
    if err:
        return err
    out = _with_mine([m], member)[0]
    out.update(
        {
            "teamName": services.team_name(t),
            "coach": who["coach"],
            "inside": who["inside"],
        }
    )
    if not who["inside"]:
        return jsonify(out)
    team = services.players(t)
    answers = list(
        db.session.scalars(select(TeamsAnswer).where(TeamsAnswer.match_id == m.id))
    )
    picks = list(
        db.session.scalars(
            select(TeamsPick).where(TeamsPick.match_id == m.id).order_by(TeamsPick.sort)
        )
    )
    rides = list(
        db.session.scalars(
            select(TeamsRide)
            .where(TeamsRide.match_id == m.id)
            .order_by(TeamsRide.created_at)
        )
    )
    seats = list(
        db.session.scalars(
            select(TeamsSeat).where(TeamsSeat.ride_id.in_([r.id for r in rides] or [0]))
        )
    )
    names = _names(
        set(team)
        | {a.member_id for a in answers}
        | {p.member_id for p in picks}
        | {r.driver_id for r in rides}
        | {s.member_id for s in seats}
    )
    answered = {a.member_id for a in answers}
    out["answers"] = sorted(
        (
            {
                "memberId": a.member_id,
                "name": names.get(a.member_id, "?"),
                "answer": a.answer,
                "note": a.note,
            }
            for a in answers
        ),
        key=lambda a: a["name"].lower(),
    )
    out["unanswered"] = sorted(
        (
            {"memberId": mid, "name": names.get(mid, "?")}
            for mid in team
            if mid not in answered
        ),
        key=lambda a: a["name"].lower(),
    )
    if who["coach"] or m.lineup_published_at:
        out["lineup"] = [
            {
                "memberId": p.member_id,
                "name": names.get(p.member_id, "?"),
                "role": p.role,
                "position": p.position,
            }
            for p in picks
        ]
    by_ride: dict[int, list] = {}
    for s in seats:
        by_ride.setdefault(s.ride_id, []).append(
            {"memberId": s.member_id, "name": names.get(s.member_id, "?")}
        )
    out["rides"] = [
        {
            "id": r.id,
            "driverId": r.driver_id,
            "driver": names.get(r.driver_id, "?"),
            "seats": r.seats,
            "fromPlace": r.from_place,
            "departs": r.departs,
            "note": r.note,
            "riders": by_ride.get(r.id, []),
            "mine": r.driver_id == member.id,
        }
        for r in rides
    ]
    return jsonify(out)


@teams_bp.patch("/matches/<int:match_id>")
@permission_required(*COACH, allow=_coach_match)
def update_match(match_id: int):
    member = get_current_member()
    m, t, who, err = _visible_match(match_id)
    if err:
        return err
    if not (who["coach"] or _can(member, services.TEAMS)):
        return api_error("FORBIDDEN", "only the team's coaches", 403)
    was_cancelled = m.cancelled
    _match_fields(m, _body(), creating=False)
    services.mirror(m, t)
    if m.cancelled and not was_cancelled:
        label = f"{m.opponent}, {m.starts_at.strftime('%d.%m. %H:%M')}"
        notify(
            services.players(t),
            lambda de: ("Spiel abgesagt", label) if de else ("Match called off", label),
            f"/app/teams/matches/{m.id}",
        )
    log_audit(member.id, "teams.match.update", "TeamsMatch", m.id, m.opponent)
    db.session.commit()
    return jsonify(_with_mine([m], member)[0])


@teams_bp.delete("/matches/<int:match_id>")
@permission_required(*COACH, allow=_coach_match)
def delete_match(match_id: int):
    member = get_current_member()
    m, t, who, err = _visible_match(match_id)
    if err:
        return err
    if not (who["coach"] or _can(member, services.TEAMS)):
        return api_error("FORBIDDEN", "only the team's coaches", 403)
    services.drop_event(m)
    log_audit(member.id, "teams.match.delete", "TeamsMatch", m.id, m.opponent)
    db.session.delete(m)
    db.session.commit()
    return "", 204


@teams_bp.put("/matches/<int:match_id>/answer")
@require_member
def answer(match_id: int):
    member = get_current_member()
    m, t, who, err = _visible_match(match_id)
    if err:
        return err
    data = _body()
    target = member.id
    if data.get("memberId") not in (None, member.id):
        if not who["coach"]:
            return api_error("FORBIDDEN", "only coaches answer for others", 403)
        target = _int(data, "memberId", 1, 2**31 - 1)
        if target not in services.players(t):
            raise Invalid("memberId: not in this team")
    elif not services.in_team(member, t):
        return api_error("FORBIDDEN", "you are not in this team", 403)
    value = data.get("answer")
    if value not in ANSWERS:
        raise Invalid("answer must be yes, maybe or no")
    if m.cancelled:
        return api_error("MATCH_CANCELLED", "this match is called off", 409)
    row = db.session.scalar(
        select(TeamsAnswer)
        .where(TeamsAnswer.match_id == m.id)
        .where(TeamsAnswer.member_id == target)
    )
    if row is None:
        row = TeamsAnswer(match_id=m.id, member_id=target)
        db.session.add(row)
    row.answer = value
    row.note = _text(data, "note", 300)
    row.updated_at = datetime.now(timezone.utc)
    db.session.commit()
    return jsonify({"answer": value, "counts": _counts([m.id]).get(m.id)})


@teams_bp.put("/matches/<int:match_id>/lineup")
@permission_required(*COACH, allow=_coach_match)
def lineup(match_id: int):
    member = get_current_member()
    m, t, who, err = _visible_match(match_id)
    if err:
        return err
    if not who["coach"]:
        return api_error("FORBIDDEN", "only the team's coaches", 403)
    data = _body()
    picks = data.get("picks")
    if not isinstance(picks, list) or len(picks) > 100:
        raise Invalid("picks must be a list")
    team = set(services.players(t))
    seen: set[int] = set()
    rows: list[TeamsPick] = []
    for i, p in enumerate(picks):
        if not isinstance(p, dict):
            raise Invalid("each pick is an object")
        mid = _int(p, "memberId", 1, 2**31 - 1)
        if mid not in team:
            raise Invalid("memberId: not in this team")
        if mid in seen:
            raise Invalid("a player is picked twice")
        seen.add(mid)
        role = p.get("role") or "starter"
        if role not in ROLES:
            raise Invalid("role must be starter or sub")
        rows.append(
            TeamsPick(
                match_id=m.id,
                member_id=mid,
                role=role,
                position=_text(p, "position", 40),
                sort=i,
            )
        )
    before = set(
        db.session.scalars(
            select(TeamsPick.member_id).where(TeamsPick.match_id == m.id)
        )
    )
    for old in db.session.scalars(select(TeamsPick).where(TeamsPick.match_id == m.id)):
        db.session.delete(old)
    db.session.flush()
    db.session.add_all(rows)
    publish = _bool(data, "publish")
    first = publish and m.lineup_published_at is None
    if publish:
        m.lineup_published_at = m.lineup_published_at or datetime.now(timezone.utc)
    elif "publish" in data:
        m.lineup_published_at = None
    if m.lineup_published_at is not None:
        # Tell the newly picked (everyone on the first publish).
        news = seen if first else seen - before
        label = f"{services.team_name(t)} – {m.opponent}, {m.starts_at.strftime('%d.%m. %H:%M')}"
        notify(
            news,
            lambda de: (
                ("Du bist aufgestellt", label)
                if de
                else ("You're in the line-up", label)
            ),
            f"/app/teams/matches/{m.id}",
        )
    log_audit(member.id, "teams.lineup", "TeamsMatch", m.id, f"{len(rows)} picked")
    db.session.commit()
    return get_match(match_id)


# ── Carpooling ───────────────────────────────────────────────────────────────


_TIME = re.compile(r"([01]\d|2[0-3]):[0-5]\d")


@teams_bp.post("/matches/<int:match_id>/rides")
@require_member
def offer_ride(match_id: int):
    member = get_current_member()
    m, t, who, err = _visible_match(match_id)
    if err:
        return err
    if not who["inside"]:
        return api_error("FORBIDDEN", "you are not in this team", 403)
    data = _body()
    departs = _text(data, "departs", 5)
    if departs and not _TIME.fullmatch(departs):
        raise Invalid("departs must be a time (HH:MM)")
    ride = TeamsRide(
        match_id=m.id,
        driver_id=member.id,
        seats=_int(data, "seats", 1, 60, None) or 0,
        from_place=_text(data, "fromPlace", 200),
        departs=departs,
        note=_text(data, "note", 300),
    )
    if not ride.seats:
        raise Invalid("seats is required")
    db.session.add(ride)
    db.session.commit()
    return get_match(match_id), 201


@teams_bp.delete("/rides/<int:ride_id>")
@require_member
def withdraw_ride(ride_id: int):
    member = get_current_member()
    ride, err = _get(TeamsRide, ride_id)
    if err:
        return err
    m = db.session.get(TeamsMatch, ride.match_id)
    t = db.session.get(TeamsTeam, m.team_id)
    if ride.driver_id != member.id and not services.is_coach(member, t):
        return api_error("FORBIDDEN", "not your ride", 403)
    riders = list(
        db.session.scalars(
            select(TeamsSeat.member_id).where(TeamsSeat.ride_id == ride.id)
        )
    )
    driver = _names([ride.driver_id]).get(ride.driver_id, "")
    notify(
        riders,
        lambda de: (
            ("Mitfahrt fällt weg", f"{driver}: {m.opponent}")
            if de
            else ("Ride cancelled", f"{driver}: {m.opponent}")
        ),
        f"/app/teams/matches/{m.id}",
    )
    db.session.delete(ride)
    db.session.commit()
    return "", 204


@teams_bp.put("/rides/<int:ride_id>/seat")
@require_member
def take_seat(ride_id: int):
    member = get_current_member()
    ride = db.session.scalar(
        select(TeamsRide).where(TeamsRide.id == ride_id).with_for_update()
    )
    if ride is None:
        return api_error("NOT_FOUND", "not found", 404)
    m = db.session.get(TeamsMatch, ride.match_id)
    t = db.session.get(TeamsTeam, m.team_id)
    if not (services.in_team(member, t) or services.is_coach(member, t)):
        return api_error("FORBIDDEN", "you are not in this team", 403)
    if ride.driver_id == member.id:
        raise Invalid("you drive this car")
    # One seat per match: taking this one gives back any other.
    for other in db.session.scalars(
        select(TeamsSeat)
        .join(TeamsRide, TeamsRide.id == TeamsSeat.ride_id)
        .where(TeamsRide.match_id == m.id)
        .where(TeamsSeat.member_id == member.id)
    ):
        if other.ride_id == ride.id:
            return get_match(m.id)
        db.session.delete(other)
    taken = db.session.scalar(
        select(func.count()).select_from(TeamsSeat).where(TeamsSeat.ride_id == ride.id)
    )
    if taken >= ride.seats:
        db.session.rollback()
        return api_error("RIDE_FULL", "this car is full", 409)
    db.session.add(TeamsSeat(ride_id=ride.id, member_id=member.id))
    db.session.commit()
    return get_match(m.id)


@teams_bp.delete("/rides/<int:ride_id>/seat")
@require_member
def leave_seat(ride_id: int):
    member = get_current_member()
    seat = db.session.scalar(
        select(TeamsSeat)
        .where(TeamsSeat.ride_id == ride_id)
        .where(TeamsSeat.member_id == member.id)
    )
    ride, err = _get(TeamsRide, ride_id)
    if err:
        return err
    if seat is not None:
        db.session.delete(seat)
        db.session.commit()
    return get_match(ride.match_id)
