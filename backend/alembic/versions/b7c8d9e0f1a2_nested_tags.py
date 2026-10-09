"""Add one-level parent/child tags.

Revision ID: b7c8d9e0f1a2
Revises: a5b6c7d8e9f0
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7c8d9e0f1a2"
down_revision: str | None = "a5b6c7d8e9f0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table(
            "tags",
            naming_convention={"uq": "uq_%(table_name)s_%(column_0_name)s"},
        ) as batch_op:
            batch_op.drop_constraint("uq_tags_normalized_name", type_="unique")
            batch_op.add_column(sa.Column("parent_id", sa.String(length=36), nullable=True))
            batch_op.create_foreign_key(
                "fk_tags_parent_id_tags", "tags", ["parent_id"], ["id"], ondelete="RESTRICT"
            )
    else:
        op.drop_constraint("tags_normalized_name_key", "tags", type_="unique")
        op.add_column("tags", sa.Column("parent_id", sa.String(length=36), nullable=True))
        op.create_foreign_key(
            "fk_tags_parent_id_tags", "tags", "tags", ["parent_id"], ["id"], ondelete="RESTRICT"
        )

    op.drop_index("ix_tags_normalized_name", table_name="tags")
    op.create_index("ix_tags_parent_id", "tags", ["parent_id"])
    op.create_index(
        "uq_tags_root_normalized_name",
        "tags",
        ["normalized_name"],
        unique=True,
        sqlite_where=sa.text("parent_id IS NULL"),
        postgresql_where=sa.text("parent_id IS NULL"),
    )
    op.create_index(
        "uq_tags_child_normalized_name",
        "tags",
        ["parent_id", "normalized_name"],
        unique=True,
        sqlite_where=sa.text("parent_id IS NOT NULL"),
        postgresql_where=sa.text("parent_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_tags_child_normalized_name", table_name="tags")
    op.drop_index("uq_tags_root_normalized_name", table_name="tags")
    op.drop_index("ix_tags_parent_id", table_name="tags")
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("tags") as batch_op:
            batch_op.drop_constraint("fk_tags_parent_id_tags", type_="foreignkey")
            batch_op.drop_column("parent_id")
            batch_op.create_unique_constraint("uq_tags_normalized_name", ["normalized_name"])
    else:
        op.drop_constraint("fk_tags_parent_id_tags", "tags", type_="foreignkey")
        op.drop_column("tags", "parent_id")
        op.create_unique_constraint("tags_normalized_name_key", "tags", ["normalized_name"])
    op.create_index("ix_tags_normalized_name", "tags", ["normalized_name"])
