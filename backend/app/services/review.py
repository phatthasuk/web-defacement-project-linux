import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.status import (
    STATUS_ACKNOWLEDGED,
    STATUS_CHANGED,
    STATUS_CHECKING,
    STATUS_DEFACED,
    STATUS_OK,
    is_valid_transition,
    require_valid_transition,
)
from app.models import CheckResult, Snapshot, Target, User
from app.services.audit import (
    ACTION_BASELINE_APPROVED,
    ACTION_CHECK_ACKNOWLEDGED,
    ACTION_DEFACEMENT_CONFIRMED,
    record_baseline_cap_demotions,
    record_review_event,
)
from app.services.checks import prune_baselines
from app.services.concurrency import is_target_in_flight

logger = logging.getLogger(__name__)


def approve_baseline(
    db: Session,
    target_id: str,
    snapshot_id: str,
    settings: Settings | None = None,
    actor: User | None = None,
) -> Snapshot:
    settings = settings or get_settings()

    target = db.get(Target, target_id)
    if target is None:
        raise NotFoundError(f"Target not found: {target_id}")

    if target.status == STATUS_CHECKING or is_target_in_flight(target_id):
        raise ConflictError("Cannot approve a baseline while a check is in progress")

    snapshot = db.get(Snapshot, snapshot_id)
    if snapshot is None:
        raise NotFoundError(f"Snapshot not found: {snapshot_id}")
    if snapshot.target_id != target_id:
        raise ValidationError("Cannot approve a snapshot for a different target")
    if snapshot.url_revision != target.url_revision:
        raise ValidationError("Cannot approve a snapshot from a previous target URL")
    if snapshot.http_status is None or not 200 <= snapshot.http_status < 300:
        raise ValidationError("Only a successful HTTP response can become a baseline")

    cap = settings.MAX_BASELINES_PER_TARGET
    if cap < 1:
        raise ValidationError(f"MAX_BASELINES_PER_TARGET must be at least 1, got {cap}")

    # Reject if candidate is older than all active baselines and would be pruned immediately
    active_baselines = list(
        db.scalars(
            select(Snapshot)
            .where(
                Snapshot.target_id == target_id,
                Snapshot.url_revision == target.url_revision,
                Snapshot.is_baseline.is_(True),
            )
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
    status_before = target.status
    baseline_ids_before = [baseline.id for baseline in active_baselines]
    was_baseline = snapshot.is_baseline
    snapshot.is_baseline = True
    db.flush()
    demoted = prune_baselines(db, target_id, target.url_revision, cap)
    if demoted:
        logger.info(
            "Target %s reached the %d-baseline cap; demoted %s",
            target_id,
            cap,
            ", ".join(demoted),
        )

    latest_check = get_latest_check_result(db, target_id)

    if not active_baselines:
        require_valid_transition(target.status, STATUS_OK)
        target.status = STATUS_OK
        target.last_error = None

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

    baseline_ids_after = [i for i in baseline_ids_before if i not in demoted]
    if snapshot_id not in baseline_ids_after:
        baseline_ids_after.append(snapshot_id)
    record_review_event(
        db,
        actor,
        ACTION_BASELINE_APPROVED,
        target_id=target_id,
        before={
            "snapshot_id": snapshot_id,
            "is_baseline": was_baseline,
            "baseline_ids": baseline_ids_before,
            "target_status": status_before,
        },
        after={
            "snapshot_id": snapshot_id,
            "is_baseline": True,
            "baseline_ids": baseline_ids_after,
            "target_status": target.status,
        },
    )
    record_baseline_cap_demotions(
        db,
        actor,
        target_id=target_id,
        demoted_snapshot_ids=demoted,
        caused_by_snapshot_id=snapshot_id,
    )

    db.commit()
    db.refresh(snapshot)
    return snapshot


def acknowledge_check_result(
    db: Session, check_result_id: str, actor: User | None = None
) -> CheckResult:
    check_result = db.get(CheckResult, check_result_id)
    if check_result is None:
        raise NotFoundError(f"CheckResult not found: {check_result_id}")

    target = db.get(Target, check_result.target_id)
    if target is None:
        raise NotFoundError(f"Target not found: {check_result.target_id}")

    if check_result.acknowledged_at is not None:
        return check_result

    status_before = target.status
    check_result.acknowledged_at = datetime.now(UTC)

    latest_check = get_latest_check_result(db, check_result.target_id)
    if latest_check is not None and latest_check.id == check_result.id:
        if is_valid_transition(target.status, STATUS_ACKNOWLEDGED):
            target.status = STATUS_ACKNOWLEDGED

    record_review_event(
        db,
        actor,
        ACTION_CHECK_ACKNOWLEDGED,
        target_id=check_result.target_id,
        before={"check_id": check_result_id, "acknowledged": False, "target_status": status_before},
        after={"check_id": check_result_id, "acknowledged": True, "target_status": target.status},
    )
    db.commit()
    db.refresh(check_result)
    return check_result


def confirm_defacement(db: Session, check_result_id: str, actor: User | None = None) -> CheckResult:
    check_result = db.get(CheckResult, check_result_id)
    if check_result is None:
        raise NotFoundError(f"CheckResult not found: {check_result_id}")

    target = db.get(Target, check_result.target_id)
    if target is None:
        raise NotFoundError(f"Target not found: {check_result.target_id}")

    status_before = target.status
    was_acknowledged = check_result.acknowledged_at is not None
    if check_result.acknowledged_at is None:
        check_result.acknowledged_at = datetime.now(UTC)

    latest_check = get_latest_check_result(db, check_result.target_id)
    if latest_check is not None and latest_check.id == check_result.id:
        if is_valid_transition(target.status, STATUS_DEFACED):
            target.status = STATUS_DEFACED

    record_review_event(
        db,
        actor,
        ACTION_DEFACEMENT_CONFIRMED,
        target_id=check_result.target_id,
        before={
            "check_id": check_result_id,
            "acknowledged": was_acknowledged,
            "target_status": status_before,
        },
        after={"check_id": check_result_id, "acknowledged": True, "target_status": target.status},
    )
    db.commit()
    db.refresh(check_result)
    return check_result


def get_latest_check_result(db: Session, target_id: str) -> CheckResult | None:
    target = db.get(Target, target_id)
    if target is None:
        return None
    return db.scalar(
        select(CheckResult)
        .where(
            CheckResult.target_id == target_id,
            CheckResult.current_snapshot_id.in_(
                select(Snapshot.id).where(
                    Snapshot.target_id == target_id,
                    Snapshot.url_revision == target.url_revision,
                )
            ),
        )
        .order_by(CheckResult.created_at.desc(), CheckResult.id.desc())
    )
