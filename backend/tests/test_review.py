from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.status import (
    STATUS_ACKNOWLEDGED,
    STATUS_CHANGED,
    STATUS_DEFACED,
    STATUS_OK,
)
from app.db.session import Base
from app.models import CheckResult, Snapshot, Target
from app.services.review import acknowledge_check_result, approve_baseline, confirm_defacement


def make_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return session_local()


def test_approve_baseline_adds_to_baseline_set_and_acknowledges_related_check():
    db = make_session()
    target = create_target(db, status=STATUS_CHANGED)
    old_snapshot = create_snapshot(db, target.id, "old", is_baseline=True)
    new_snapshot = create_snapshot(db, target.id, "new", is_baseline=False)
    unrelated_snapshot = create_snapshot(db, target.id, "unrelated", is_baseline=False)
    related_check = create_check_result(
        db,
        target.id,
        baseline_snapshot_id=old_snapshot.id,
        current_snapshot_id=new_snapshot.id,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    unrelated_check = create_check_result(
        db,
        target.id,
        baseline_snapshot_id=old_snapshot.id,
        current_snapshot_id=unrelated_snapshot.id,
        created_at=datetime(2026, 1, 2, tzinfo=UTC),
    )

    approved = approve_baseline(db, target.id, new_snapshot.id)

    db.refresh(old_snapshot)
    db.refresh(related_check)
    db.refresh(unrelated_check)
    db.refresh(target)
    assert approved.id == new_snapshot.id
    assert approved.is_baseline is True
    # Approving adds a baseline rather than replacing one, so a rotating page can
    # keep an approved variant per appearance (below MAX_BASELINES_PER_TARGET).
    assert old_snapshot.is_baseline is True
    # new_snapshot was NOT for the latest check (unrelated_check on Jan 2 is latest),
    # so target status remains CHANGED to avoid masking the latest unresolved alert.
    assert target.status == STATUS_CHANGED
    assert related_check.acknowledged_at is not None
    assert unrelated_check.acknowledged_at is None

    # Approving the snapshot of the latest check resolves the change and sets target to OK
    approved_latest = approve_baseline(db, target.id, unrelated_snapshot.id)
    db.refresh(target)
    db.refresh(unrelated_check)
    assert approved_latest.is_baseline is True
    assert target.status == STATUS_OK
    assert unrelated_check.acknowledged_at is not None



def test_approve_baseline_rejects_cross_target_snapshot():
    db = make_session()
    target = create_target(db, status=STATUS_CHANGED)
    other_target = create_target(db, name="Other", status=STATUS_CHANGED)
    other_snapshot = create_snapshot(db, other_target.id, "other", is_baseline=False)

    try:
        approve_baseline(db, target.id, other_snapshot.id)
    except ValueError as exc:
        assert "different target" in str(exc)
    else:
        raise AssertionError("Expected cross-target approval to fail")


def test_acknowledge_check_result_is_idempotent_and_updates_latest_target_status():
    db = make_session()
    target = create_target(db, status=STATUS_CHANGED)
    baseline = create_snapshot(db, target.id, "baseline", is_baseline=True)
    current = create_snapshot(db, target.id, "current", is_baseline=False)
    check_result = create_check_result(
        db,
        target.id,
        baseline_snapshot_id=baseline.id,
        current_snapshot_id=current.id,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    acknowledged = acknowledge_check_result(db, check_result.id)
    first_acknowledged_at = acknowledged.acknowledged_at
    acknowledged_again = acknowledge_check_result(db, check_result.id)

    assert first_acknowledged_at is not None
    assert acknowledged_again.acknowledged_at == first_acknowledged_at
    assert target.status == STATUS_ACKNOWLEDGED


def test_acknowledge_stale_check_does_not_override_latest_target_status():
    db = make_session()
    target = create_target(db, status=STATUS_CHANGED)
    baseline = create_snapshot(db, target.id, "baseline", is_baseline=True)
    old_current = create_snapshot(db, target.id, "old-current", is_baseline=False)
    latest_current = create_snapshot(db, target.id, "latest-current", is_baseline=False)
    old_check = create_check_result(
        db,
        target.id,
        baseline_snapshot_id=baseline.id,
        current_snapshot_id=old_current.id,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    create_check_result(
        db,
        target.id,
        baseline_snapshot_id=baseline.id,
        current_snapshot_id=latest_current.id,
        created_at=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=1),
    )

    acknowledged = acknowledge_check_result(db, old_check.id)

    assert acknowledged.acknowledged_at is not None
    assert target.status == STATUS_CHANGED


def test_confirm_defacement_updates_target_status_and_sets_acknowledged_at():
    db = make_session()
    target = create_target(db, status=STATUS_CHANGED)
    baseline = create_snapshot(db, target.id, "baseline", is_baseline=True)
    current = create_snapshot(db, target.id, "current", is_baseline=False)
    check_result = create_check_result(
        db,
        target.id,
        baseline_snapshot_id=baseline.id,
        current_snapshot_id=current.id,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    result = confirm_defacement(db, check_result.id)

    assert result.acknowledged_at is not None
    assert target.status == STATUS_DEFACED

    # Idempotent call
    result_again = confirm_defacement(db, check_result.id)
    assert result_again.acknowledged_at == result.acknowledged_at
    assert target.status == STATUS_DEFACED


def test_confirm_defacement_transitions_from_acknowledged():
    db = make_session()
    target = create_target(db, status=STATUS_ACKNOWLEDGED)
    baseline = create_snapshot(db, target.id, "baseline", is_baseline=True)
    current = create_snapshot(db, target.id, "current", is_baseline=False)
    check_result = create_check_result(
        db,
        target.id,
        baseline_snapshot_id=baseline.id,
        current_snapshot_id=current.id,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    check_result.acknowledged_at = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    db.commit()

    result = confirm_defacement(db, check_result.id)

    assert target.status == STATUS_DEFACED
    assert result.acknowledged_at is not None


def test_confirm_defacement_stale_check_does_not_override_latest_target_status():
    db = make_session()
    target = create_target(db, status=STATUS_CHANGED)
    baseline = create_snapshot(db, target.id, "baseline", is_baseline=True)
    old_current = create_snapshot(db, target.id, "old-current", is_baseline=False)
    latest_current = create_snapshot(db, target.id, "latest-current", is_baseline=False)
    old_check = create_check_result(
        db,
        target.id,
        baseline_snapshot_id=baseline.id,
        current_snapshot_id=old_current.id,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    create_check_result(
        db,
        target.id,
        baseline_snapshot_id=baseline.id,
        current_snapshot_id=latest_current.id,
        created_at=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=1),
    )

    result = confirm_defacement(db, old_check.id)

    assert result.acknowledged_at is not None
    assert target.status == STATUS_CHANGED


def create_target(db: Session, name: str = "Example", status: str = STATUS_OK) -> Target:
    target = Target(name=name, url=f"https://{name.lower()}.example.com", status=status)
    db.add(target)
    db.commit()
    db.refresh(target)
    return target


def create_snapshot(
    db: Session,
    target_id: str,
    snapshot_id: str,
    is_baseline: bool,
) -> Snapshot:
    snapshot = Snapshot(
        id=snapshot_id,
        target_id=target_id,
        final_url="https://example.com",
        http_status=200,
        title="Example",
        screenshot_path=f"/tmp/{snapshot_id}.png",
        text_path=f"/tmp/{snapshot_id}.txt",
        html_path=f"/tmp/{snapshot_id}.html",
        is_baseline=is_baseline,
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return snapshot


def create_check_result(
    db: Session,
    target_id: str,
    baseline_snapshot_id: str,
    current_snapshot_id: str,
    created_at: datetime,
) -> CheckResult:
    check_result = CheckResult(
        target_id=target_id,
        baseline_snapshot_id=baseline_snapshot_id,
        current_snapshot_id=current_snapshot_id,
        created_at=created_at,
        status=STATUS_CHANGED,
        text_change_score=1.0,
        visual_change_score=1.0,
        summary="Changed",
    )
    db.add(check_result)
    db.commit()
    db.refresh(check_result)
    return check_result


def test_acknowledge_check_result_when_target_failed_leaves_failed_status():
    from app.core.status import STATUS_FAILED
    db = make_session()
    target = create_target(db, status=STATUS_FAILED)
    baseline = create_snapshot(db, target.id, "baseline", is_baseline=True)
    current = create_snapshot(db, target.id, "current", is_baseline=False)
    check_result = create_check_result(
        db,
        target.id,
        baseline_snapshot_id=baseline.id,
        current_snapshot_id=current.id,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    acknowledged = acknowledge_check_result(db, check_result.id)

    assert acknowledged.acknowledged_at is not None
    assert target.status == STATUS_FAILED


def test_approve_baseline_from_failed_status_succeeds_and_preserves_error():
    from app.core.status import STATUS_FAILED
    db = make_session()
    target = create_target(db, status=STATUS_FAILED)
    target.last_error = "DNS resolution failed"
    db.commit()

    create_snapshot(db, target.id, "baseline", is_baseline=True)
    new_snapshot = create_snapshot(db, target.id, "new", is_baseline=False)

    approved = approve_baseline(db, target.id, new_snapshot.id)

    db.refresh(target)
    assert approved.id == new_snapshot.id
    assert target.status == STATUS_FAILED
    assert target.last_error == "DNS resolution failed"


def test_approve_baseline_while_checking_raises_validation_error():
    from app.core.errors import ValidationError
    from app.core.status import STATUS_CHECKING

    db = make_session()
    target = create_target(db, status=STATUS_CHECKING)

    create_snapshot(db, target.id, "baseline", is_baseline=True)
    new_snapshot = create_snapshot(db, target.id, "new", is_baseline=False)

    try:
        approve_baseline(db, target.id, new_snapshot.id)
    except ValidationError as exc:
        assert "while a check is in progress" in str(exc)
    else:
        raise AssertionError("Expected approve_baseline while Checking to raise ValidationError")




def test_approve_baseline_demotes_oldest_beyond_the_cap():
    db = make_session()
    target = create_target(db, status=STATUS_CHANGED)
    oldest = create_snapshot_at(db, target.id, "oldest", is_baseline=True, minutes_old=40)
    middle = create_snapshot_at(db, target.id, "middle", is_baseline=True, minutes_old=30)
    newest_approved = create_snapshot_at(db, target.id, "newest", is_baseline=True, minutes_old=20)
    candidate = create_snapshot_at(db, target.id, "candidate", is_baseline=False, minutes_old=10)

    approve_baseline(db, target.id, candidate.id, settings=Settings(MAX_BASELINES_PER_TARGET=3))

    for snapshot in (oldest, middle, newest_approved, candidate):
        db.refresh(snapshot)

    # Newest three stay baselines; the oldest is demoted but not deleted.
    assert candidate.is_baseline is True
    assert newest_approved.is_baseline is True
    assert middle.is_baseline is True
    assert oldest.is_baseline is False
    assert db.get(Snapshot, oldest.id) is not None


def test_approve_baseline_keeps_a_single_baseline_when_cap_is_one():
    db = make_session()
    target = create_target(db, status=STATUS_CHANGED)
    previous = create_snapshot_at(db, target.id, "previous", is_baseline=True, minutes_old=20)
    candidate = create_snapshot_at(db, target.id, "candidate", is_baseline=False, minutes_old=10)

    approve_baseline(db, target.id, candidate.id, settings=Settings(MAX_BASELINES_PER_TARGET=1))

    db.refresh(previous)
    db.refresh(candidate)
    assert candidate.is_baseline is True
    assert previous.is_baseline is False


def create_snapshot_at(
    db: Session,
    target_id: str,
    snapshot_id: str,
    is_baseline: bool,
    minutes_old: int,
) -> Snapshot:
    """Snapshot with an explicit age, so baseline ordering is deterministic."""
    snapshot = Snapshot(
        id=snapshot_id,
        target_id=target_id,
        captured_at=datetime.now(UTC) - timedelta(minutes=minutes_old),
        final_url="https://example.com",
        http_status=200,
        title="Example",
        screenshot_path=f"/tmp/{snapshot_id}.png",
        text_path=f"/tmp/{snapshot_id}.txt",
        html_path=f"/tmp/{snapshot_id}.html",
        is_baseline=is_baseline,
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return snapshot


def test_approve_baseline_rejects_candidate_older_than_cap():
    from app.core.errors import ValidationError
    db = make_session()
    target = create_target(db, status=STATUS_CHANGED)
    # Active baselines at minutes 30, 20, 10
    create_snapshot_at(db, target.id, "b1", is_baseline=True, minutes_old=30)
    create_snapshot_at(db, target.id, "b2", is_baseline=True, minutes_old=20)
    create_snapshot_at(db, target.id, "b3", is_baseline=True, minutes_old=10)
    # Candidate older than all kept baselines (50 min old)
    old_candidate = create_snapshot_at(
        db, target.id, "old-candidate", is_baseline=False, minutes_old=50
    )

    try:
        approve_baseline(
            db, target.id, old_candidate.id, settings=Settings(MAX_BASELINES_PER_TARGET=3)
        )
    except ValidationError as exc:
        assert "older than" in str(exc)
    else:
        raise AssertionError("Expected ValidationError when candidate is older than baseline cap")

    db.refresh(old_candidate)
    assert old_candidate.is_baseline is False


def test_approve_baseline_rejects_zero_or_negative_cap():
    from app.core.errors import ValidationError
    db = make_session()
    target = create_target(db, status=STATUS_CHANGED)
    snap = create_snapshot(db, target.id, "snap", is_baseline=False)

    try:
        approve_baseline(db, target.id, snap.id, settings=Settings(MAX_BASELINES_PER_TARGET=0))
    except ValidationError as exc:
        assert "at least 1" in str(exc)
    else:
        raise AssertionError("Expected ValidationError for cap < 1")


def test_approve_baseline_transitions_from_defaced_and_acknowledged():
    db = make_session()
    # Test from DEFACED
    target_defaced = create_target(db, name="DefacedTarget", status=STATUS_DEFACED)
    base1 = create_snapshot(db, target_defaced.id, "base1", is_baseline=True)
    cur1 = create_snapshot(db, target_defaced.id, "cur1", is_baseline=False)
    chk1 = create_check_result(
        db,
        target_defaced.id,
        baseline_snapshot_id=base1.id,
        current_snapshot_id=cur1.id,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    approve_baseline(db, target_defaced.id, cur1.id)
    db.refresh(target_defaced)
    db.refresh(chk1)
    assert target_defaced.status == STATUS_OK
    assert chk1.acknowledged_at is not None

    # Test from ACKNOWLEDGED
    target_ack = create_target(db, name="AckTarget", status=STATUS_ACKNOWLEDGED)
    base2 = create_snapshot(db, target_ack.id, "base2", is_baseline=True)
    cur2 = create_snapshot(db, target_ack.id, "cur2", is_baseline=False)
    chk2 = create_check_result(
        db,
        target_ack.id,
        baseline_snapshot_id=base2.id,
        current_snapshot_id=cur2.id,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    approve_baseline(db, target_ack.id, cur2.id)
    db.refresh(target_ack)
    db.refresh(chk2)
    assert target_ack.status == STATUS_OK
    assert chk2.acknowledged_at is not None

