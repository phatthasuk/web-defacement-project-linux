"""Persist check schedules and individual attempt history.

Revision ID: 7e3a9c2f1b64
Revises: c9d0e1f2a3b4
Create Date: 2026-10-15
"""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa

from alembic import op

revision: str = "7e3a9c2f1b64"
down_revision: str | None = "c9d0e1f2a3b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("targets", sa.Column("last_error_code", sa.String(length=60), nullable=True))
    op.add_column("targets", sa.Column("last_http_status", sa.Integer(), nullable=True))
    op.add_column("targets", sa.Column("next_check_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("targets", sa.Column("check_run_id", sa.String(length=36), nullable=True))
    op.add_column("targets", sa.Column("check_run_source", sa.String(length=20), nullable=True))
    op.add_column(
        "targets",
        sa.Column("check_attempt_count", sa.Integer(), nullable=False, server_default="0"),
    )
    targets = sa.table(
        "targets",
        sa.column("is_active", sa.Boolean()),
        sa.column("next_check_at", sa.DateTime(timezone=True)),
    )
    op.execute(
        targets.update()
        .where(targets.c.is_active.is_(True))
        .values(next_check_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=1))
    )

    op.create_table(
        "check_attempts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("target_id", sa.String(length=36), nullable=False),
        sa.Column("url_revision", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("error_code", sa.String(length=60), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("check_result_id", sa.String(length=36), nullable=True),
        sa.Column("snapshot_id", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(["target_id"], ["targets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["check_result_id"], ["check_results.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["snapshot_id"], ["snapshots.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_check_attempts_target_id", "check_attempts", ["target_id"])
    op.create_index("ix_check_attempts_run_id", "check_attempts", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_check_attempts_run_id", table_name="check_attempts")
    op.drop_index("ix_check_attempts_target_id", table_name="check_attempts")
    op.drop_table("check_attempts")
    op.drop_column("targets", "check_attempt_count")
    op.drop_column("targets", "check_run_source")
    op.drop_column("targets", "check_run_id")
    op.drop_column("targets", "next_check_at")
    op.drop_column("targets", "last_http_status")
    op.drop_column("targets", "last_error_code")
