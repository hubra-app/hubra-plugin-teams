"""teams, matches, answers, picks, rides and seats

Runs in public and in every club's schema, tracked in its own version table
(alembic_version_teams). has_table() keeps it safe to run twice.

Revision ID: 8d4f1a6c3e27
Revises:
Create Date: 2026-11-05 15:00:00

"""

from alembic import op
import sqlalchemy as sa

from hubra.core.plugins.ops import has_table

revision = "8d4f1a6c3e27"
down_revision = None
branch_labels = None
depends_on = None


def _ts(name, nullable=True):
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def _id():
    return sa.Column("id", sa.Integer(), nullable=False)


def _match():
    return (
        sa.Column("match_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["match_id"], ["teams_matches.id"], ondelete="CASCADE"),
    )


def _member(name="member_id"):
    return (
        sa.Column(name, sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint([name], ["members.id"], ondelete="CASCADE"),
    )


def upgrade():
    if not has_table("teams_teams"):
        op.create_table(
            "teams_teams",
            _id(),
            sa.Column("group_id", sa.Integer(), nullable=False),
            sa.Column("feed_url", sa.String(500), nullable=True),
            sa.Column("feed_name", sa.String(120), nullable=True),
            _ts("feed_synced_at"),
            sa.Column("feed_error", sa.String(300), nullable=True),
            sa.Column("home_location", sa.String(200), nullable=True),
            sa.Column("in_calendar", sa.Boolean(), nullable=False),
            _ts("created_at", nullable=False),
            sa.ForeignKeyConstraint(["group_id"], ["groups.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("group_id"),
            sa.PrimaryKeyConstraint("id"),
        )
    if not has_table("teams_matches"):
        op.create_table(
            "teams_matches",
            _id(),
            sa.Column("team_id", sa.Integer(), nullable=False),
            sa.Column("opponent", sa.String(200), nullable=False),
            sa.Column("home", sa.Boolean(), nullable=True),
            sa.Column("starts_at", sa.DateTime(), nullable=False),
            sa.Column("meet_at", sa.DateTime(), nullable=True),
            sa.Column("location", sa.String(300), nullable=True),
            sa.Column("competition", sa.String(120), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("cancelled", sa.Boolean(), nullable=False),
            sa.Column("score_us", sa.Integer(), nullable=True),
            sa.Column("score_them", sa.Integer(), nullable=True),
            sa.Column("feed_uid", sa.String(300), nullable=True),
            sa.Column("event_id", sa.Integer(), nullable=True),
            _ts("lineup_published_at"),
            _ts("reminded_at"),
            _ts("created_at", nullable=False),
            sa.ForeignKeyConstraint(
                ["team_id"], ["teams_teams.id"], ondelete="CASCADE"
            ),
            sa.UniqueConstraint("team_id", "feed_uid", name="uq_teams_feed_uid"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_teams_matches_team_start", "teams_matches", ["team_id", "starts_at"]
        )
    if not has_table("teams_answers"):
        op.create_table(
            "teams_answers",
            _id(),
            *_match(),
            *_member(),
            sa.Column("answer", sa.String(8), nullable=False),
            sa.Column("note", sa.String(300), nullable=True),
            _ts("updated_at", nullable=False),
            sa.UniqueConstraint("match_id", "member_id", name="uq_teams_answer"),
            sa.PrimaryKeyConstraint("id"),
        )
    if not has_table("teams_picks"):
        op.create_table(
            "teams_picks",
            _id(),
            *_match(),
            *_member(),
            sa.Column("role", sa.String(8), nullable=False),
            sa.Column("position", sa.String(40), nullable=True),
            sa.Column("sort", sa.Integer(), nullable=False),
            sa.UniqueConstraint("match_id", "member_id", name="uq_teams_pick"),
            sa.PrimaryKeyConstraint("id"),
        )
    if not has_table("teams_rides"):
        op.create_table(
            "teams_rides",
            _id(),
            *_match(),
            *_member("driver_id"),
            sa.Column("seats", sa.Integer(), nullable=False),
            sa.Column("from_place", sa.String(200), nullable=True),
            sa.Column("departs", sa.String(5), nullable=True),
            sa.Column("note", sa.String(300), nullable=True),
            _ts("created_at", nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    if not has_table("teams_seats"):
        op.create_table(
            "teams_seats",
            _id(),
            sa.Column("ride_id", sa.Integer(), nullable=False),
            *_member(),
            sa.ForeignKeyConstraint(
                ["ride_id"], ["teams_rides.id"], ondelete="CASCADE"
            ),
            sa.UniqueConstraint("ride_id", "member_id", name="uq_teams_seat"),
            sa.PrimaryKeyConstraint("id"),
        )


def downgrade():
    for table in (
        "teams_seats",
        "teams_rides",
        "teams_picks",
        "teams_answers",
        "teams_matches",
        "teams_teams",
    ):
        if has_table(table):
            op.drop_table(table)
