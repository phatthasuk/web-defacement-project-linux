"""Scope snapshots and baselines to the target URL revision.

Revision ID: e3c4d5e6f7a8
Revises: d2b3c4e5f6a7
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e3c4d5e6f7a8"
down_revision: str | None = "d2b3c4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("targets") as batch_op:
        batch_op.add_column(
            sa.Column("url_revision", sa.Integer(), nullable=False, server_default="1")
        )
    with op.batch_alter_table("snapshots") as batch_op:
        batch_op.add_column(
            sa.Column("url_revision", sa.Integer(), nullable=False, server_default="1")
        )


def downgrade() -> None:
    with op.batch_alter_table("snapshots") as batch_op:
        batch_op.drop_column("url_revision")
    with op.batch_alter_table("targets") as batch_op:
        batch_op.drop_column("url_revision")
