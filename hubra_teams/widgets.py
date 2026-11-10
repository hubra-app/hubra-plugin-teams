"""Dashboard widgets of Teams (docs/dashboards.md in hubra-app/hubra).

teams.matches  list  the next matches, of the viewer's teams by default,
                     with time, place and the viewer's own answer

They read as the viewing member; every member with Teams sees them.
"""

from __future__ import annotations

from sqlalchemy import select

from hubra.core.extensions import db
from hubra.core.models.group import Group, GroupMembership

from . import services
from .models import TeamsAnswer, TeamsMatch, TeamsTeam

_ANSWER = {
    True: {"yes": "Dabei", "maybe": "Vielleicht", "no": "Nicht dabei", None: "Noch offen"},
    False: {"yes": "In", "maybe": "Maybe", "no": "Out", None: "Not answered"},
}


def _german(member) -> bool:
    return (getattr(member, "language", None) or "de").lower().startswith("de")


def _count(config: dict) -> int:
    try:
        return max(1, min(int(config.get("count") or 5), 20))
    except (TypeError, ValueError):
        return 5


def matches(ctx, config: dict) -> dict:
    """Matches ahead, not cancelled; only the viewer's teams unless ``mine`` is off."""
    query = (
        select(TeamsMatch, TeamsTeam, Group.name)
        .join(TeamsTeam, TeamsTeam.id == TeamsMatch.team_id)
        .join(Group, Group.id == TeamsTeam.group_id)
        .where(TeamsMatch.starts_at >= services.local_now())
        .where(TeamsMatch.cancelled.is_(False))
        .order_by(TeamsMatch.starts_at, TeamsMatch.id)
    )
    me = ctx.actor
    if config.get("mine", True) and me is not None:
        query = query.where(
            TeamsTeam.group_id.in_(
                select(GroupMembership.group_id).where(GroupMembership.member_id == me.id)
            )
        )
    rows = db.session.execute(query.limit(_count(config))).all()
    answers = {}
    if me is not None and rows:
        answers = dict(
            db.session.execute(
                select(TeamsAnswer.match_id, TeamsAnswer.answer)
                .where(TeamsAnswer.member_id == me.id)
                .where(TeamsAnswer.match_id.in_([m.id for m, _, _ in rows]))
            ).all()
        )
    german = _german(me)
    items = []
    for match, _team, name in rows:
        where = "vs" if match.home is not False else "@"
        parts = [f"{match.starts_at:%d.%m. %H:%M}", match.location]
        if me is not None and services.in_team(me, _team):
            parts.append(_ANSWER[german].get(answers.get(match.id)))
        items.append(
            {
                "label": f"{name} {where} {match.opponent}",
                "sub": " · ".join(p for p in parts if p),
                "path": f"/app/teams/matches/{match.id}",
            }
        )
    return {"items": items, "total": len(items)}
