"""Audit events for review and baseline decisions.

These decisions decide what the detectors treat as "normal", so who made one and
what changed has to be answerable later. Events are only added to the caller's
session: they commit or roll back together with the change they describe, so a
failed change never leaves a success event behind.

Only IDs and states are recorded, never URLs or page content.
"""

from collections.abc import Sequence

from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.models import MemberAuditEvent, User

ACTION_BASELINE_APPROVED = "baseline.approved"
ACTION_BASELINE_DEMOTED = "baseline.demoted"
ACTION_CHECK_ACKNOWLEDGED = "check.acknowledged"
ACTION_DEFACEMENT_CONFIRMED = "check.defacement_confirmed"

SOURCE_APPLICATION = "application"
# A baseline pushed out by MAX_BASELINES_PER_TARGET when another one was approved.
SOURCE_BASELINE_CAP = "baseline_cap"


def record_review_event(
    db: Session,
    actor: User | None,
    action: str,
    *,
    target_id: str,
    before: dict[str, object] | None = None,
    after: dict[str, object] | None = None,
    source: str = SOURCE_APPLICATION,
) -> None:
    db.add(
        MemberAuditEvent(
            actor_id=actor.id if actor else None,
            action=action,
            target_id=target_id,
            source=source,
            occurred_at=utcnow(),
            before=before,
            after=after,
        )
    )


def record_baseline_cap_demotions(
    db: Session,
    actor: User | None,
    *,
    target_id: str,
    demoted_snapshot_ids: Sequence[str],
    caused_by_snapshot_id: str,
) -> None:
    for snapshot_id in demoted_snapshot_ids:
        record_review_event(
            db,
            actor,
            ACTION_BASELINE_DEMOTED,
            target_id=target_id,
            before={"snapshot_id": snapshot_id, "is_baseline": True},
            after={
                "snapshot_id": snapshot_id,
                "is_baseline": False,
                "caused_by_snapshot_id": caused_by_snapshot_id,
            },
            source=SOURCE_BASELINE_CAP,
        )
