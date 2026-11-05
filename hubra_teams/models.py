"""The Teams tables (one copy per club schema).

Match times are the club's wall-clock time, stored without a zone.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from hubra.core.extensions import db


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _member_fk() -> ForeignKey:
    return ForeignKey("members.id", ondelete="CASCADE")


class TeamsTeam(db.Model):
    """A group that plays matches."""

    __tablename__ = "teams_teams"

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(
        ForeignKey("groups.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    # The league's iCal feed (https or webcal) and how this team is named in it.
    feed_url: Mapped[str | None] = mapped_column(String(500))
    feed_name: Mapped[str | None] = mapped_column(String(120))
    feed_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    feed_error: Mapped[str | None] = mapped_column(String(300))
    home_location: Mapped[str | None] = mapped_column(String(200))
    # Matches also go into the club calendar (Anlässe).
    in_calendar: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )


class TeamsMatch(db.Model):
    __tablename__ = "teams_matches"
    __table_args__ = (
        UniqueConstraint("team_id", "feed_uid", name="uq_teams_feed_uid"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(
        ForeignKey("teams_teams.id", ondelete="CASCADE"), nullable=False
    )
    opponent: Mapped[str] = mapped_column(String(200), nullable=False)
    # True at home, False away, None when the feed doesn't say.
    home: Mapped[bool | None] = mapped_column(Boolean)
    starts_at: Mapped[datetime] = mapped_column(DateTime(), nullable=False)
    meet_at: Mapped[datetime | None] = mapped_column(DateTime())
    location: Mapped[str | None] = mapped_column(String(300))
    competition: Mapped[str | None] = mapped_column(String(120))
    notes: Mapped[str | None] = mapped_column(Text)
    cancelled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    score_us: Mapped[int | None] = mapped_column(Integer)
    score_them: Mapped[int | None] = mapped_column(Integer)
    feed_uid: Mapped[str | None] = mapped_column(String(300))
    # The mirrored club event, if any (no foreign key: events may be off).
    event_id: Mapped[int | None] = mapped_column(Integer)
    lineup_published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    reminded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )


class TeamsAnswer(db.Model):
    """A player's yes, maybe or no for one match."""

    __tablename__ = "teams_answers"
    __table_args__ = (
        UniqueConstraint("match_id", "member_id", name="uq_teams_answer"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(
        ForeignKey("teams_matches.id", ondelete="CASCADE"), nullable=False
    )
    member_id: Mapped[int] = mapped_column(_member_fk(), nullable=False)
    answer: Mapped[str] = mapped_column(String(8), nullable=False)
    note: Mapped[str | None] = mapped_column(String(300))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )


class TeamsPick(db.Model):
    """A player in the line-up: a starter or a substitute."""

    __tablename__ = "teams_picks"
    __table_args__ = (UniqueConstraint("match_id", "member_id", name="uq_teams_pick"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(
        ForeignKey("teams_matches.id", ondelete="CASCADE"), nullable=False
    )
    member_id: Mapped[int] = mapped_column(_member_fk(), nullable=False)
    role: Mapped[str] = mapped_column(String(8), nullable=False)
    position: Mapped[str | None] = mapped_column(String(40))
    sort: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class TeamsRide(db.Model):
    """A driver's offer of seats to a match."""

    __tablename__ = "teams_rides"

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(
        ForeignKey("teams_matches.id", ondelete="CASCADE"), nullable=False
    )
    driver_id: Mapped[int] = mapped_column(_member_fk(), nullable=False)
    seats: Mapped[int] = mapped_column(Integer, nullable=False)
    from_place: Mapped[str | None] = mapped_column(String(200))
    departs: Mapped[str | None] = mapped_column(String(5))
    note: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )


class TeamsSeat(db.Model):
    __tablename__ = "teams_seats"
    __table_args__ = (UniqueConstraint("ride_id", "member_id", name="uq_teams_seat"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    ride_id: Mapped[int] = mapped_column(
        ForeignKey("teams_rides.id", ondelete="CASCADE"), nullable=False
    )
    member_id: Mapped[int] = mapped_column(_member_fk(), nullable=False)
