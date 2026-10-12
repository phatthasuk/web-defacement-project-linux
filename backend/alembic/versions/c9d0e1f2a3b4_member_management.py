"""Add approved members, website assignments, and administrative audit events.

Revision ID: c9d0e1f2a3b4
Revises: f4e5f6a7b8c9

For an existing database, set MEMBER_ROLE_MAPPING to a JSON object mapping
verified usernames to "admin" or "operator" before upgrading, for example:
{"known-bootstrap": "admin"}. Every unspecified legacy account becomes an
Operator. At least one mapped Admin must already be active. Empty databases do
not require a mapping.
"""

from __future__ import annotations

import json
import os
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c9d0e1f2a3b4"
down_revision: str | None = "b7c8d9e0f1a2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    # Do not infer privileges from the historical free-text role column. A
    # verified account mapping must identify every Admin explicitly.
    rows = list(bind.execute(sa.text("SELECT id, username, is_active FROM users")))
    mapping_raw = os.environ.get("MEMBER_ROLE_MAPPING", "").strip()
    if rows and not mapping_raw:
        raise RuntimeError(
            "MEMBER_ROLE_MAPPING is required for a non-empty legacy database; "
            "map verified usernames explicitly before upgrading"
        )
    mapping = json.loads(mapping_raw) if mapping_raw else {}
    if not isinstance(mapping, dict) or any(
        role not in {"admin", "operator"} for role in mapping.values()
    ):
        raise RuntimeError("MEMBER_ROLE_MAPPING must map usernames to admin or operator")
    usernames = {row.username for row in rows}
    if any(username not in usernames for username in mapping):
        raise RuntimeError("MEMBER_ROLE_MAPPING contains a username not present in users")
    active_admins = {
        row.username for row in rows if row.is_active and mapping.get(row.username) == "admin"
    }
    if rows and not active_admins:
        raise RuntimeError("MEMBER_ROLE_MAPPING must identify at least one active Admin")

    now = sa.text("CURRENT_TIMESTAMP")
    with op.batch_alter_table("users") as batch:
        batch.add_column(
            sa.Column("display_name", sa.String(100), nullable=False, server_default="")
        )
        batch.add_column(
            sa.Column(
                "registration_status", sa.String(20), nullable=False, server_default="approved"
            )
        )
        batch.add_column(sa.Column("registration_reviewed_by", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("registration_reviewed_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("registration_rejection_reason", sa.Text(), nullable=True))
        batch.add_column(
            sa.Column(
                "must_change_password", sa.Boolean(), nullable=False, server_default=sa.false()
            )
        )
        batch.add_column(sa.Column("password_changed_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("last_login_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("created_at", sa.DateTime(), nullable=False, server_default=now))
        batch.add_column(sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=now))

    for row in rows:
        role = mapping.get(row.username, "operator")
        bind.execute(
            sa.text(
                "UPDATE users SET role=:role, display_name=:name, "
                "registration_status='approved' WHERE id=:id"
            ),
            {"role": role, "name": row.username, "id": row.id},
        )
    bind.execute(
        sa.text(
            "UPDATE sessions SET revoked_at=CURRENT_TIMESTAMP, "
            "revocation_reason='member_management_migration' WHERE revoked_at IS NULL"
        )
    )

    with op.batch_alter_table("users") as batch:
        batch.create_foreign_key(
            "fk_users_registration_reviewed_by_users",
            "users",
            ["registration_reviewed_by"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_check_constraint("ck_users_role_fixed", "role IN ('admin', 'operator')")
        batch.create_check_constraint(
            "ck_users_registration_status",
            "registration_status IN ('pending', 'approved', 'rejected')",
        )
        batch.create_check_constraint(
            "ck_users_pending_rejected_inactive",
            "registration_status = 'approved' OR is_active = 0",
        )

    op.create_table(
        "user_target_assignments",
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column(
            "target_id",
            sa.String(36),
            sa.ForeignKey("targets.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("assigned_at", sa.DateTime(), nullable=False, server_default=now),
    )
    op.create_index(
        "ix_user_target_assignments_target_id", "user_target_assignments", ["target_id"]
    )
    op.create_table(
        "member_audit_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "actor_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column(
            "member_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column(
            "target_id",
            sa.String(36),
            sa.ForeignKey("targets.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("source", sa.String(40), nullable=False, server_default="application"),
        sa.Column("occurred_at", sa.DateTime(), nullable=False, server_default=now),
        sa.Column("before", sa.JSON(), nullable=True),
        sa.Column("after", sa.JSON(), nullable=True),
        sa.Column("details", sa.Text(), nullable=True),
    )
    op.create_index("ix_member_audit_events_member_id", "member_audit_events", ["member_id"])
    op.create_index("ix_member_audit_events_target_id", "member_audit_events", ["target_id"])
    op.create_index("ix_member_audit_events_occurred_at", "member_audit_events", ["occurred_at"])


def downgrade() -> None:
    op.drop_index("ix_member_audit_events_occurred_at", table_name="member_audit_events")
    op.drop_index("ix_member_audit_events_target_id", table_name="member_audit_events")
    op.drop_index("ix_member_audit_events_member_id", table_name="member_audit_events")
    op.drop_table("member_audit_events")
    op.drop_index("ix_user_target_assignments_target_id", table_name="user_target_assignments")
    op.drop_table("user_target_assignments")
    with op.batch_alter_table("users") as batch:
        batch.drop_constraint("ck_users_pending_rejected_inactive", type_="check")
        batch.drop_constraint("ck_users_registration_status", type_="check")
        batch.drop_constraint("ck_users_role_fixed", type_="check")
        batch.drop_constraint("fk_users_registration_reviewed_by_users", type_="foreignkey")
        for name in (
            "updated_at",
            "created_at",
            "last_login_at",
            "password_changed_at",
            "must_change_password",
            "registration_rejection_reason",
            "registration_reviewed_at",
            "registration_reviewed_by",
            "registration_status",
            "display_name",
        ):
            batch.drop_column(name)
