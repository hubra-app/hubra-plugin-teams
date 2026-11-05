"""Shared parts: who coaches, the club calendar mirror, feed sync, reminders."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from flask import current_app
from sqlalchemy import select

from hubra.core.extensions import db
from hubra.core.models.group import Group, GroupMembership
from hubra.core.models.member import Member

from . import feed
from .models import TeamsAnswer, TeamsMatch, TeamsTeam
from .notify import notify

MATCHES = "teams.matches.update"
TEAMS = "teams.teams.update"
REMIND_BEFORE = timedelta(days=3)


def zone() -> ZoneInfo:
    try:
        return ZoneInfo(current_app.config.get("MAIL_TIMEZONE") or "Europe/Zurich")
    except Exception:  # noqa: BLE001 - a bad setting falls back
        return ZoneInfo("Europe/Zurich")


def local_now() -> datetime:
    return datetime.now(zone()).replace(tzinfo=None, microsecond=0)


def players(team: TeamsTeam) -> list[int]:
    """The team's active members."""
    return list(
        db.session.scalars(
            select(GroupMembership.member_id)
            .join(Member, Member.id == GroupMembership.member_id)
            .where(GroupMembership.group_id == team.group_id)
            .where(Member.status == "active")
            .where(Member.archived_at.is_(None))
        )
    )


def is_coach(member, team: TeamsTeam) -> bool:
    from hubra.core.permissions import member_has_permission

    if member is None:
        return False
    if member_has_permission(member, MATCHES):
        return True
    group = db.session.get(Group, team.group_id)
    return group is not None and group.lead_id == member.id


def in_team(member, team: TeamsTeam) -> bool:
    return member is not None and (
        db.session.scalar(
            select(GroupMembership.id)
            .where(GroupMembership.group_id == team.group_id)
            .where(GroupMembership.member_id == member.id)
        )
        is not None
    )


def team_name(team: TeamsTeam) -> str:
    group = db.session.get(Group, team.group_id)
    return group.name if group else "Team"


# ── The club calendar ────────────────────────────────────────────────────────


def _event_type() -> str:
    from hubra.core.schemas.event import club_event_types

    types = club_event_types()
    for t in types:
        if re.search(r"match|spiel|wettkampf|game|turnier", t, re.IGNORECASE):
            return t
    return types[0]


def mirror(match: TeamsMatch, team: TeamsTeam) -> None:
    """Keeps the match's club event in step, when the team shows its matches
    in the calendar and the events module is on."""
    from hubra.core.models.event import ClubEvent
    from hubra.core.modules import is_enabled

    event = db.session.get(ClubEvent, match.event_id) if match.event_id else None
    wanted = team.in_calendar and not match.cancelled and is_enabled("events")
    if not wanted:
        if event is not None:
            db.session.delete(event)
        match.event_id = None
        return
    name = team_name(team)
    if match.home is False:
        title = f"{match.opponent} – {name}"
    else:
        title = f"{name} – {match.opponent}"
    if event is None:
        event = ClubEvent(type=_event_type(), category="competition")
        db.session.add(event)
    event.title = title[:255]
    event.date = match.starts_at.date()
    event.time = match.starts_at.strftime("%H:%M")
    event.location = (match.location or "")[:255] or None
    event.group_id = team.group_id
    event.category = "competition"
    event.description = match.competition
    db.session.flush()
    match.event_id = event.id


def drop_event(match: TeamsMatch) -> None:
    from hubra.core.models.event import ClubEvent

    if match.event_id:
        event = db.session.get(ClubEvent, match.event_id)
        if event is not None:
            db.session.delete(event)
        match.event_id = None


# ── Feeds ────────────────────────────────────────────────────────────────────


def sync(team: TeamsTeam, text: str | None = None) -> dict:
    """Reads the team's feed: new matches are added, moved ones updated,
    future ones that left the feed are marked cancelled. *text* skips the
    download (tests)."""
    if not team.feed_url:
        raise feed.FeedError("This team has no calendar link")
    if text is None:
        text = feed.fetch(team.feed_url)
    events = feed.parse(text, zone())
    now = local_now()
    known = {
        m.feed_uid: m
        for m in db.session.scalars(
            select(TeamsMatch)
            .where(TeamsMatch.team_id == team.id)
            .where(TeamsMatch.feed_uid.is_not(None))
        )
    }
    added = updated = cancelled = 0
    seen = set()
    for ev in events:
        seen.add(ev.uid)
        opponent, home = feed.split_summary(ev.summary, team.feed_name)
        match = known.get(ev.uid)
        location = ev.location or (team.home_location if home else None)
        if match is None:
            if ev.starts_at < now - timedelta(days=1):
                continue  # don't fill the list with last season
            match = TeamsMatch(
                team_id=team.id,
                feed_uid=ev.uid,
                opponent=opponent or "?",
                home=home,
                starts_at=ev.starts_at,
                location=location,
                cancelled=ev.cancelled,
            )
            db.session.add(match)
            db.session.flush()
            added += 1
        else:
            before = (
                match.opponent,
                match.home,
                match.starts_at,
                match.location,
                match.cancelled,
            )
            match.opponent = opponent or match.opponent
            match.home = home if home is not None else match.home
            match.starts_at = ev.starts_at
            match.location = location or match.location
            match.cancelled = ev.cancelled
            if before != (
                match.opponent,
                match.home,
                match.starts_at,
                match.location,
                match.cancelled,
            ):
                updated += 1
        mirror(match, team)
    for uid, match in known.items():
        if uid not in seen and match.starts_at > now and not match.cancelled:
            match.cancelled = True
            mirror(match, team)
            cancelled += 1
    team.feed_synced_at = datetime.now(timezone.utc)
    team.feed_error = None
    return {"added": added, "updated": updated, "cancelled": cancelled}


def sync_all() -> dict:
    done = {"teams": 0, "failed": 0}
    for team in db.session.scalars(
        select(TeamsTeam).where(TeamsTeam.feed_url.is_not(None))
    ):
        try:
            with db.session.begin_nested():
                sync(team)
            done["teams"] += 1
        except feed.FeedError as exc:
            team.feed_error = str(exc)[:300]
            done["failed"] += 1
    return done


# ── Reminders ────────────────────────────────────────────────────────────────


def remind() -> int:
    """Three days before a match, players who haven't answered get a bell."""
    now = local_now()
    sent = 0
    for match in db.session.scalars(
        select(TeamsMatch)
        .where(TeamsMatch.cancelled.is_(False))
        .where(TeamsMatch.reminded_at.is_(None))
        .where(TeamsMatch.starts_at > now)
        .where(TeamsMatch.starts_at <= now + REMIND_BEFORE)
    ):
        team = db.session.get(TeamsTeam, match.team_id)
        answered = set(
            db.session.scalars(
                select(TeamsAnswer.member_id).where(TeamsAnswer.match_id == match.id)
            )
        )
        missing = [m for m in players(team) if m not in answered]
        label = f"{match.opponent}, {match.starts_at.strftime('%d.%m. %H:%M')}"
        sent += notify(
            missing,
            lambda de: (
                ("Bist du dabei?", f"{team_name(team)} gegen {label}")
                if de
                else ("Can you play?", f"{team_name(team)} against {label}")
            ),
            f"/app/teams/matches/{match.id}",
        )
        match.reminded_at = datetime.now(timezone.utc)
    return sent
