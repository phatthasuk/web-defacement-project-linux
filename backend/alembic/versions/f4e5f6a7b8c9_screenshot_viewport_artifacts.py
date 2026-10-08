"""Store raw screenshot evidence alongside viewport-normalised screenshots.

Revision ID: f4e5f6a7b8c9
Revises: e3c4d5e6f7a8
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f4e5f6a7b8c9"
down_revision: str | None = "e3c4d5e6f7a8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("snapshots") as batch_op:
        batch_op.add_column(sa.Column("raw_screenshot_path", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("viewport_width", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("document_width", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("screenshot_format_version", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("snapshots") as batch_op:
        batch_op.drop_column("screenshot_format_version")
        batch_op.drop_column("document_width")
        batch_op.drop_column("viewport_width")
        batch_op.drop_column("raw_screenshot_path")
