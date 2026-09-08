"""Add the structural detector: target allowlist and check_results score

Revision ID: d2b3c4e5f6a7
Revises: c1a2b3d4e5f6
Create Date: 2026-09-02 16:00:00.000000

Adds the two columns the structural detector needs:

- targets.allowed_domains — hosts whose scripts/iframes/forms/links are expected
  on that target, so a site's own third parties are not reported every check.
- check_results.structure_change_score — the score from comparing the two
  snapshots' HTML structure.

Both are additive. Existing check_results rows get 0.0, which reads as "no
structural change" rather than as a finding, since those checks were run before
the detector existed.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d2b3c4e5f6a7"
down_revision: str | None = "c1a2b3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # batch_alter_table so SQLite (which cannot ALTER in place) is supported.
    with op.batch_alter_table("targets", schema=None) as batch_op:
        batch_op.add_column(sa.Column("allowed_domains", sa.JSON(), nullable=True))

    with op.batch_alter_table("check_results", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "structure_change_score",
                sa.Float(),
                nullable=False,
                server_default="0.0",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("check_results", schema=None) as batch_op:
        batch_op.drop_column("structure_change_score")

    with op.batch_alter_table("targets", schema=None) as batch_op:
        batch_op.drop_column("allowed_domains")
