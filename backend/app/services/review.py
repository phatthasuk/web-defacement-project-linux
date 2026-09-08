import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import NotFoundError, ValidationError
from app.core.status import (
    STATUS_ACKNOWLEDGED,
    STATUS_CHANGED,
    STATUS_CHECKING,
    STATUS_DEFACED,
    STATUS_NEVER_CHECKED,
    STATUS_OK,
    is_valid_transition,
    require_valid_transition,
)
from app.models import CheckResult, Snapshot, Target
from app.services.checks import prune_baselines

logger = logging.getLogger(__name__)


def approve_baseline(
    db: Session,
    target_id: str,
    snapshot_id: str,
    settings: Settings | None = None,
) -> Snapshot:
    settings = settings or get_settings()

    target = db.get(Target, target_id)
    if target is None:
        raise NotFoundError(f"Target not found: {target_id}")

    if target.status == STATUS_CHECKING:
        raise ValidationError("Cannot approve a baseline while a check is in progress")

    snapshot = db.get(Snapshot, snapshot_id)
    if snapshot is None:
        raise NotFoundError(f"Snapshot not found: {snapshot_id}")
    if snapshot.target_id != target_id:
        raise ValidationError("Cannot approve a snapshot for a different target")

    if target.status == STATUS_NEVER_CHECKED:
        require_valid_transition(target.status, STATUS_OK)

    cap = settings.MAX_BASELINES_PER_TARGET
    if cap < 1:
        raise ValidationError(f"MAX_BASELINES_PER_TARGET must be at least 1, got {cap}")

    # Reject if candidate is older than all active baselines and would be pruned immediately
    active_baselines = list(
        db.scalars(
            select(Snapshot)
            .where(Snapshot.target_id == target_id, Snapshot.is_baseline.is_(True))
            .order_by(Snapshot.captured_at.desc(), Snapshot.id.desc())
        )
    )
    if not snapshot.is_baseline and len(active_baselines) >= cap:
        oldest_kept = active_baselines[cap - 1]
        candidate_key = (snapshot.captured_at, snapshot.id)
        oldest_key = (oldest_kept.captured_at, oldest_kept.id)
        if candidate_key < oldest_key:
            raise ValidationError(
                f"Cannot approve snapshot: it is older than the {cap} active baselines "
                "and would be pruned immediately"
            )

    # Approving *adds* to the target's baseline set instead of replacing it, so a
    # page with legitimately rotating content can hold one approved baseline per
    # variant. The oldest are demoted once the configured cap is reached.
    snapshot.is_baseline = True
    db.flush()
    demoted = prune_baselines(db, target_id, cap)
    if demoted:
        logger.info(
            "Target %s reached the %d-baseline cap; demoted %s",
            target_id,
            cap,
            ", ".join(demoted),
        )

    latest_check = db.scalar(
        select(CheckResult)
        .where(CheckResult.target_id == target_id)
        .order_by(CheckResult.created_at.desc(), CheckResult.id.desc())
    )

    if latest_check is not None and latest_check.current_snapshot_id == snapshot_id:
        if latest_check.acknowledged_at is None:
            latest_check.acknowledged_at = datetime.now(UTC)
        if target.status in (STATUS_CHANGED, STATUS_ACKNOWLEDGED, STATUS_DEFACED):
            require_valid_transition(target.status, STATUS_OK)
            target.status = STATUS_OK
            target.last_error = None
    else:
        related_check = db.scalar(
            select(CheckResult)
            .where(
                CheckResult.target_id == target_id,
                CheckResult.current_snapshot_id == snapshot_id,
                CheckResult.acknowledged_at.is_(None),
            )
            .order_by(CheckResult.created_at.desc(), CheckResult.id.desc())
        )
        if related_check is not None:
            related_check.acknowledged_at = datetime.now(UTC)

    db.commit()
    db.refresh(snapshot)
    return snapshot


def acknowledge_check_result(db: Session, check_result_id: str) -> CheckResult:
    check_result = db.get(CheckResult, check_result_id)
    if check_result is None:
        raise NotFoundError(f"CheckResult not found: {check_result_id}")

    target = db.get(Target, check_result.target_id)
    if target is None:
        raise NotFoundError(f"Target not found: {check_result.target_id}")

    if check_result.acknowledged_at is not None:
        return check_result

    check_result.acknowledged_at = datetime.now(UTC)

    latest_check = get_latest_check_result(db, check_result.target_id)
    if latest_check is not None and latest_check.id == check_result.id:
        if is_valid_transition(target.status, STATUS_ACKNOWLEDGED):
            target.status = STATUS_ACKNOWLEDGED

    db.commit()
    db.refresh(check_result)
    return check_result


def confirm_defacement(db: Session, check_result_id: str) -> CheckResult:
    check_result = db.get(CheckResult, check_result_id)
    if check_result is None:
        raise NotFoundError(f"CheckResult not found: {check_result_id}")

    target = db.get(Target, check_result.target_id)
    if target is None:
        raise NotFoundError(f"Target not found: {check_result.target_id}")

    if check_result.acknowledged_at is None:
        check_result.acknowledged_at = datetime.now(UTC)

    latest_check = get_latest_check_result(db, check_result.target_id)
    if latest_check is not None and latest_check.id == check_result.id:
        if is_valid_transition(target.status, STATUS_DEFACED):
            target.status = STATUS_DEFACED

    db.commit()
    db.refresh(check_result)
    return check_result


def get_latest_check_result(db: Session, target_id: str) -> CheckResult | None:
    return db.scalar(
        select(CheckResult)
        .where(CheckResult.target_id == target_id)
        .order_by(CheckResult.created_at.desc(), CheckResult.id.desc())
    )
