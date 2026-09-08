"""Add session CSRF token, session->user FK, and user lockout fields

Revision ID: c1a2b3d4e5f6
Revises: b958b19b16a2
Create Date: 2026-07-10 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c1a2b3d4e5f6"
down_revision: str | None = "b958b19b16a2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("sessions", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("csrf_token", sa.String(), nullable=False, server_default="")
        )
        batch_op.create_foreign_key(
            "fk_sessions_user_id_users", "users", ["user_id"], ["id"]
        )

    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "failed_login_count",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )
        batch_op.add_column(
            sa.Column("first_failed_login_at", sa.DateTime(), nullable=True)
        )
        batch_op.add_column(sa.Column("locked_until", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("locked_until")
        batch_op.drop_column("first_failed_login_at")
        batch_op.drop_column("failed_login_count")

    with op.batch_alter_table("sessions", schema=None) as batch_op:
        batch_op.drop_constraint("fk_sessions_user_id_users", type_="foreignkey")
        batch_op.drop_column("csrf_token")
