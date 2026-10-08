"""Add shared tags and website tag associations.

Revision ID: a5b6c7d8e9f0
Revises: f4e5f6a7b8c9
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a5b6c7d8e9f0"
down_revision: str | None = "f4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tags",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("normalized_name", sa.String(length=50), nullable=False),
        sa.Column("color_key", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("normalized_name"),
    )
    op.create_index("ix_tags_normalized_name", "tags", ["normalized_name"])
    op.create_table(
        "target_tags",
        sa.Column("target_id", sa.String(length=36), nullable=False),
        sa.Column("tag_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["tag_id"], ["tags.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_id"], ["targets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("target_id", "tag_id"),
    )
    op.create_index("ix_target_tags_tag_id", "target_tags", ["tag_id"])


def downgrade() -> None:
    op.drop_index("ix_target_tags_tag_id", table_name="target_tags")
    op.drop_table("target_tags")
    op.drop_index("ix_tags_normalized_name", table_name="tags")
    op.drop_table("tags")
