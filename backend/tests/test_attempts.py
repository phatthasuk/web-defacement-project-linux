"""Durable check attempt tests across independent SQLAlchemy sessions."""

from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from PIL import Image
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.errors import CaptureBudgetExceeded, ScreenshotCaptureError, SsrfBlockedError
from app.core.status import STATUS_CHANGED, STATUS_OK
from app.core.time import utcnow
from app.db.session import Base
from app.models import CheckAttempt, CheckResult, Snapshot, Target
from app.services.attempts import (
    _is_retryable,
    _recover_attempt_finalization_failure,
    run_check_attempt,
)
from app.services.capture.capture import CaptureResult
from app.services.checks import (
    TargetCheckResult,
    classify_capture_error,
    recover_stale_checks,
    run_target_check,
)
from app.services.concurrency import try_acquire_in_flight
from app.services.review import approve_baseline
from app.services.scheduler import CheckScheduler


def make_db(tmp_path: Path) -> tuple[sessionmaker[Session], object]:
    engine = create_engine(f"sqlite:///{tmp_path / f'{uuid4()}.db'}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=True), engine


def make_capture(out_dir: Path, snapshot_id: str, text: str, color: str) -> CaptureResult:
    screenshot_path = out_dir / "screenshots" / f"{snapshot_id}.png"
    text_path = out_dir / "text" / f"{snapshot_id}.txt"
    html_path = out_dir / "html" / f"{snapshot_id}.html"
    screenshot_path.parent.mkdir(parents=True, exist_ok=True)
    text_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (2, 2), color).save(screenshot_path)
    text_path.write_text(text, encoding="utf-8")
    html_path.write_text(f"<html><body>{text}</body></html>", encoding="utf-8")
    return CaptureResult(
        id=snapshot_id,
        url="https://example.com",
        final_url="https://example.com",
        http_status=200,
        title="Example",
        screenshot_path=str(screenshot_path),
        text_path=str(text_path),
        html_path=str(html_path),
        redirect_count=0,
    )


def test_only_the_recognized_screenshot_capture_error_is_retryable() -> None:
    code, retryable = classify_capture_error(
        ScreenshotCaptureError(
            "Page.screenshot: Protocol error (Page.captureScreenshot): "
            "Unable to capture screenshot"
        )
    )
    assert code == "screenshot_capture_failed"
    assert retryable and _is_retryable(code)

    budget_code, budget_retryable = classify_capture_error(
        CaptureBudgetExceeded("screenshot exceeds budget")
    )
    ssrf_code, ssrf_retryable = classify_capture_error(SsrfBlockedError("blocked by SSRF guard"))
    assert not budget_retryable and not _is_retryable(budget_code)
    assert not ssrf_retryable and not _is_retryable(ssrf_code)
    assert not _is_retryable("internal_error")


async def test_ok_attempt_records_primitive_ids_and_next_schedule(tmp_path: Path) -> None:
    session_factory, engine = make_db(tmp_path)
    settings = Settings(
        DATA_DIR=str(tmp_path), CHECK_INTERVAL_SECONDS=3600, CHECK_JITTER_MAX_SECONDS=0
    )
    try:
        with session_factory() as db:
            target = Target(name="Example", url="https://example.com")
            db.add(target)
            db.commit()
            target_id = target.id

        async def baseline_capture(url: str, current: Settings, out_dir: Path) -> CaptureResult:
            return make_capture(out_dir, "baseline", "Same page", "white")

        with session_factory() as db:
            target = db.get(Target, target_id)
            assert target is not None
            candidate = await run_target_check(db, target, settings, baseline_capture)
            assert candidate.snapshot_id == "baseline"
            approve_baseline(db, target_id, "baseline", settings)
            target = db.get(Target, target_id)
            assert target is not None
            target.check_run_id = "ok-run"
            target.check_run_source = "scheduled"
            target.next_check_at = None
            db.commit()

        async def unchanged_capture(url: str, current: Settings, out_dir: Path) -> CaptureResult:
            return make_capture(out_dir, "unchanged", "Same page", "white")

        assert try_acquire_in_flight(target_id)
        result = await run_check_attempt(
            target_id,
            settings,
            run_id="ok-run",
            initial_source="scheduled",
            capture_func=unchanged_capture,
            session_factory=session_factory,
        )

        assert result is not None and result.status == STATUS_OK
        with session_factory() as db:
            target = db.get(Target, target_id)
            attempt = db.scalar(select(CheckAttempt).where(CheckAttempt.target_id == target_id))
            check = db.scalar(select(CheckResult).where(CheckResult.target_id == target_id))
            baseline = db.get(Snapshot, "baseline")
            assert target is not None and target.next_check_at is not None
            assert target.next_check_at >= utcnow() + timedelta(seconds=3590)
            assert target.check_run_id is None
            assert target.check_run_source is None
            assert target.check_attempt_count == 0
            assert attempt is not None and attempt.finished_at is not None
            assert attempt.status == STATUS_OK
            assert attempt.snapshot_id == "baseline"
            assert check is not None and attempt.check_result_id == check.id
            assert baseline is not None

        with session_factory() as db:
            target = db.get(Target, target_id)
            assert target is not None
            target.next_check_at = utcnow() - timedelta(seconds=1)
            db.commit()
        scheduler = CheckScheduler(settings, session_factory=session_factory)
        with patch("app.services.scheduler.capture_snapshot", unchanged_capture):
            await scheduler._tick()
            await scheduler.stop()
        with session_factory() as db:
            target = db.get(Target, target_id)
            attempts = list(
                db.scalars(select(CheckAttempt).where(CheckAttempt.target_id == target_id))
            )
            assert target is not None and target.next_check_at is not None
            assert target.next_check_at > utcnow()
            assert len(attempts) == 2
            assert all(item.finished_at is not None for item in attempts)
    finally:
        engine.dispose()


async def test_changed_attempt_keeps_result_ids_after_snapshot_refresh_failure(
    tmp_path: Path, monkeypatch
) -> None:
    session_factory, engine = make_db(tmp_path)
    settings = Settings(
        DATA_DIR=str(tmp_path), CHECK_INTERVAL_SECONDS=3600, CHECK_JITTER_MAX_SECONDS=0
    )
    try:
        with session_factory() as db:
            target = Target(name="Example", url="https://example.com")
            db.add(target)
            db.commit()
            target_id = target.id

        async def capture(url: str, current: Settings, out_dir: Path) -> CaptureResult:
            return make_capture(out_dir, "base", "Baseline text", "white")

        with session_factory() as db:
            target = db.get(Target, target_id)
            assert target is not None
            await run_target_check(db, target, settings, capture)
            approve_baseline(db, target_id, "base", settings)
            target = db.get(Target, target_id)
            assert target is not None
            target.check_run_id = "changed-run"
            target.check_run_source = "scheduled"
            db.commit()

        original_refresh = Session.refresh

        def fail_snapshot_refresh(db: Session, instance, *args, **kwargs) -> None:
            if isinstance(instance, Snapshot):
                db.expunge(instance)
                raise RuntimeError("injected snapshot refresh failure")
            original_refresh(db, instance, *args, **kwargs)

        monkeypatch.setattr(Session, "refresh", fail_snapshot_refresh)

        async def changed_capture(url: str, current: Settings, out_dir: Path) -> CaptureResult:
            return make_capture(out_dir, "changed", "Entirely different words", "black")

        assert try_acquire_in_flight(target_id)
        result = await run_check_attempt(
            target_id,
            settings,
            run_id="changed-run",
            initial_source="scheduled",
            capture_func=changed_capture,
            session_factory=session_factory,
        )
        assert result is not None and result.status == STATUS_CHANGED
        with session_factory() as db:
            attempt = db.scalar(select(CheckAttempt).where(CheckAttempt.target_id == target_id))
            assert attempt is not None and attempt.finished_at is not None
            assert attempt.snapshot_id == "changed"
            check = db.get(CheckResult, attempt.check_result_id)
            assert check is not None and check.status == STATUS_CHANGED
    finally:
        engine.dispose()


async def test_ok_attempt_keeps_ok_status_and_ids_after_check_result_refresh_failure(
    tmp_path: Path, monkeypatch
) -> None:
    session_factory, engine = make_db(tmp_path)
    settings = Settings(
        DATA_DIR=str(tmp_path), CHECK_INTERVAL_SECONDS=3600, CHECK_JITTER_MAX_SECONDS=0
    )
    try:
        with session_factory() as db:
            target = Target(name="Example", url="https://example.com")
            db.add(target)
            db.commit()
            target_id = target.id

        async def baseline_capture(url: str, current: Settings, out_dir: Path) -> CaptureResult:
            return make_capture(out_dir, "base", "Same text", "white")

        with session_factory() as db:
            target = db.get(Target, target_id)
            assert target is not None
            await run_target_check(db, target, settings, baseline_capture)
            approve_baseline(db, target_id, "base", settings)
            target = db.get(Target, target_id)
            assert target is not None
            target.check_run_id = "ok-refresh-fail-run"
            target.check_run_source = "scheduled"
            db.commit()

        original_refresh = Session.refresh

        def fail_check_result_refresh(db: Session, instance, *args, **kwargs) -> None:
            if isinstance(instance, CheckResult):
                db.expunge(instance)
                raise RuntimeError("injected check_result refresh failure")
            original_refresh(db, instance, *args, **kwargs)

        monkeypatch.setattr(Session, "refresh", fail_check_result_refresh)

        async def unchanged_capture(url: str, current: Settings, out_dir: Path) -> CaptureResult:
            return make_capture(out_dir, "unchanged", "Same text", "white")

        assert try_acquire_in_flight(target_id)
        result = await run_check_attempt(
            target_id,
            settings,
            run_id="ok-refresh-fail-run",
            initial_source="scheduled",
            capture_func=unchanged_capture,
            session_factory=session_factory,
        )
        assert result is not None and result.status == STATUS_OK
        with session_factory() as db:
            target = db.get(Target, target_id)
            attempt = db.scalar(select(CheckAttempt).where(CheckAttempt.target_id == target_id))
            check = db.scalar(select(CheckResult).where(CheckResult.target_id == target_id))
            assert target is not None and target.status == STATUS_OK
            assert attempt is not None and attempt.finished_at is not None
            assert attempt.status == STATUS_OK
            assert attempt.snapshot_id == "base"
            assert check is not None and attempt.check_result_id == check.id
    finally:
        engine.dispose()


async def test_awaiting_baseline_attempt_records_snapshot_id_after_refresh_failure(
    tmp_path: Path, monkeypatch
) -> None:
    session_factory, engine = make_db(tmp_path)
    settings = Settings(DATA_DIR=str(tmp_path))
    try:
        with session_factory() as db:
            target = Target(name="Example", url="https://example.com")
            db.add(target)
            db.commit()
            target_id = target.id
            target.check_run_id = "baseline-run"
            db.commit()

        original_refresh = Session.refresh

        def fail_snapshot_refresh(db: Session, instance, *args, **kwargs) -> None:
            if isinstance(instance, Snapshot):
                db.expunge(instance)
                raise RuntimeError("injected snapshot refresh failure")
            original_refresh(db, instance, *args, **kwargs)

        monkeypatch.setattr(Session, "refresh", fail_snapshot_refresh)

        async def capture(url: str, current: Settings, out_dir: Path) -> CaptureResult:
            return make_capture(out_dir, "first-candidate", "First page", "white")

        assert try_acquire_in_flight(target_id)
        result = await run_check_attempt(
            target_id,
            settings,
            run_id="baseline-run",
            initial_source="scheduled",
            capture_func=capture,
            session_factory=session_factory,
        )
        assert result is not None and result.snapshot_id == "first-candidate"
        with session_factory() as db:
            attempt = db.scalar(select(CheckAttempt).where(CheckAttempt.target_id == target_id))
            assert attempt is not None and attempt.finished_at is not None
            assert attempt.snapshot_id == "first-candidate"
            assert attempt.check_result_id is None
    finally:
        engine.dispose()


async def test_attempt_finalization_failure_recovers_target_and_attempt(
    tmp_path: Path,
) -> None:
    session_factory, engine = make_db(tmp_path)
    settings = Settings(
        DATA_DIR=str(tmp_path), CHECK_INTERVAL_SECONDS=3600, CHECK_JITTER_MAX_SECONDS=0
    )
    failed_once = False

    def fail_first_finalization(db: Session) -> None:
        nonlocal failed_once
        if failed_once:
            return
        for attempt in db.dirty:
            if isinstance(attempt, CheckAttempt) and attempt.finished_at is not None:
                failed_once = True
                raise RuntimeError("injected attempt write failure")

    event.listen(Session, "before_commit", fail_first_finalization)
    try:
        with session_factory() as db:
            target = Target(name="Example", url="https://example.com")
            db.add(target)
            db.commit()
            target_id = target.id
            target.check_run_id = "failure-run"
            db.commit()

        async def capture(url: str, current: Settings, out_dir: Path) -> CaptureResult:
            return make_capture(out_dir, "candidate", "First page", "white")

        assert try_acquire_in_flight(target_id)
        result = await run_check_attempt(
            target_id,
            settings,
            run_id="failure-run",
            initial_source="scheduled",
            capture_func=capture,
            session_factory=session_factory,
        )
        assert result is not None
        assert failed_once
        with session_factory() as db:
            target = db.get(Target, target_id)
            attempt = db.scalar(select(CheckAttempt).where(CheckAttempt.target_id == target_id))
            assert target is not None and target.next_check_at is not None
            assert target.check_run_id is None
            assert target.check_run_source is None
            assert target.check_attempt_count == 0
            assert attempt is not None and attempt.finished_at is not None
            assert attempt.error_code == "attempt_persistence_error"
            assert "injected attempt write failure" in (attempt.error_message or "")
            assert attempt.status == result.status
        from app.services.check_progress import get_progress_record

        progress = get_progress_record(target_id, None, 1)
        assert progress is not None
        assert progress.state == "finished"
        assert progress.outcome == result.status
        assert progress.error_code is None
        assert not any(step.state == "running" for step in progress.steps)
    finally:
        event.remove(Session, "before_commit", fail_first_finalization)
        engine.dispose()


def test_failure_recovery_preserves_existing_retry_deadline(tmp_path: Path) -> None:
    session_factory, engine = make_db(tmp_path)
    try:
        retry_deadline = utcnow() + timedelta(seconds=30)
        with session_factory() as db:
            target = Target(
                name="Retry target",
                url="https://example.com",
                check_run_id="retry-run",
                check_run_source="scheduled",
                check_attempt_count=2,
                next_check_at=retry_deadline,
            )
            db.add(target)
            db.commit()
            target_id = target.id
            attempt = CheckAttempt(
                target_id=target_id,
                url_revision=1,
                run_id="retry-run",
                attempt_number=2,
                source="retry",
                status="Checking",
                started_at=utcnow(),
            )
            db.add(attempt)
            db.commit()
            attempt_id = attempt.id

        _recover_attempt_finalization_failure(
            target_id=target_id,
            run_id="retry-run",
            url_revision=1,
            attempt_id=attempt_id,
            result=TargetCheckResult(status=STATUS_OK, snapshot=None, check_result=None),
            error=RuntimeError("injected"),
            settings=Settings(DATA_DIR=str(tmp_path)),
            session_factory=session_factory,
        )
        with session_factory() as db:
            target = db.get(Target, target_id)
            assert target is not None and target.next_check_at == retry_deadline
            assert target.check_run_id == "retry-run"
            assert target.check_attempt_count == 2
    finally:
        engine.dispose()


def test_failure_recovery_does_not_rewrite_newer_run_or_revision(tmp_path: Path) -> None:
    session_factory, engine = make_db(tmp_path)
    try:
        with session_factory() as db:
            target = Target(
                name="New run",
                url="https://example.com",
                url_revision=2,
                check_run_id="new-run",
                next_check_at=None,
            )
            db.add(target)
            db.commit()
            target_id = target.id
            old_attempt = CheckAttempt(
                target_id=target_id,
                url_revision=1,
                run_id="old-run",
                attempt_number=1,
                source="scheduled",
                status="Checking",
                started_at=utcnow(),
            )
            db.add(old_attempt)
            db.commit()
            attempt_id = old_attempt.id

        _recover_attempt_finalization_failure(
            target_id=target_id,
            run_id="old-run",
            url_revision=1,
            attempt_id=attempt_id,
            result=TargetCheckResult(status=STATUS_OK, snapshot=None, check_result=None),
            error=RuntimeError("injected"),
            settings=Settings(DATA_DIR=str(tmp_path)),
            session_factory=session_factory,
        )
        with session_factory() as db:
            target = db.get(Target, target_id)
            assert target is not None
            assert target.check_run_id == "new-run"
            assert target.next_check_at is None
            assert target.url_revision == 2
    finally:
        engine.dispose()


def test_startup_recovery_releases_ok_target_with_unfinished_attempt(tmp_path: Path) -> None:
    session_factory, engine = make_db(tmp_path)
    try:
        with session_factory() as db:
            target = Target(
                name="Interrupted OK target",
                url="https://example.com",
                status=STATUS_OK,
                check_run_id="interrupted-run",
                check_run_source="scheduled",
                check_attempt_count=1,
            )
            db.add(target)
            db.commit()
            target_id = target.id
            db.add(
                CheckAttempt(
                    target_id=target_id,
                    url_revision=1,
                    run_id="interrupted-run",
                    attempt_number=1,
                    source="scheduled",
                    status="Checking",
                    started_at=utcnow(),
                )
            )
            db.commit()

        with session_factory() as db:
            assert recover_stale_checks(db, Settings(DATA_DIR=str(tmp_path))) == [target_id]

        with session_factory() as db:
            target = db.get(Target, target_id)
            attempt = db.scalar(select(CheckAttempt).where(CheckAttempt.target_id == target_id))
            assert target is not None and target.next_check_at is not None
            assert attempt is not None and attempt.finished_at is not None
            assert attempt.error_code == "process_interrupted"
    finally:
        engine.dispose()


async def test_screenshot_capture_failure_retries_once_and_can_succeed(tmp_path: Path) -> None:
    session_factory, engine = make_db(tmp_path)
    settings = Settings(
        DATA_DIR=str(tmp_path),
        CHECK_INTERVAL_SECONDS=3600,
        CHECK_JITTER_MAX_SECONDS=0,
        CHECK_RETRY_JITTER_MAX_SECONDS=0,
    )
    try:
        with session_factory() as db:
            target = Target(name="Screenshot retry", url="https://example.com")
            db.add(target)
            db.commit()
            target_id = target.id

        async def baseline_capture(url: str, current: Settings, out_dir: Path) -> CaptureResult:
            return make_capture(out_dir, "screenshot-retry-baseline", "Same page", "white")

        with session_factory() as db:
            target = db.get(Target, target_id)
            assert target is not None
            await run_target_check(db, target, settings, baseline_capture)
            approve_baseline(db, target_id, "screenshot-retry-baseline", settings)
            target = db.get(Target, target_id)
            assert target is not None
            target.check_run_id = "screenshot-retry-run"
            target.check_run_source = "scheduled"
            db.commit()

        async def transient_failure(url: str, current: Settings, out_dir: Path) -> CaptureResult:
            raise ScreenshotCaptureError(
                "Page.screenshot: Protocol error (Page.captureScreenshot): "
                "Unable to capture screenshot"
            )

        assert try_acquire_in_flight(target_id)
        first_result = await run_check_attempt(
            target_id,
            settings,
            run_id="screenshot-retry-run",
            initial_source="scheduled",
            capture_func=transient_failure,
            session_factory=session_factory,
        )
        assert first_result is not None and first_result.status == "Failed"
        assert first_result.error_code == "screenshot_capture_failed"

        with session_factory() as db:
            target = db.get(Target, target_id)
            assert target is not None and target.next_check_at is not None
            assert 119 <= (target.next_check_at - utcnow()).total_seconds() <= 120
            target.next_check_at = utcnow() - timedelta(seconds=1)
            db.commit()

        async def recovered_capture(url: str, current: Settings, out_dir: Path) -> CaptureResult:
            return make_capture(out_dir, "screenshot-retry-recovered", "Same page", "white")

        assert try_acquire_in_flight(target_id)
        second_result = await run_check_attempt(
            target_id,
            settings,
            run_id="screenshot-retry-run",
            initial_source="scheduled",
            capture_func=recovered_capture,
            session_factory=session_factory,
        )
        assert second_result is not None and second_result.status == STATUS_OK

        with session_factory() as db:
            attempts = list(
                db.scalars(
                    select(CheckAttempt)
                    .where(CheckAttempt.run_id == "screenshot-retry-run")
                    .order_by(CheckAttempt.attempt_number)
                )
            )
            assert len(attempts) == 2
            assert attempts[0].error_code == "screenshot_capture_failed"
            assert attempts[0].source == "scheduled"
            assert attempts[1].error_code is None
            assert attempts[1].source == "retry"
    finally:
        engine.dispose()


async def test_screenshot_capture_failure_does_not_retry_twice(tmp_path: Path) -> None:
    session_factory, engine = make_db(tmp_path)
    settings = Settings(
        DATA_DIR=str(tmp_path),
        CHECK_INTERVAL_SECONDS=3600,
        CHECK_JITTER_MAX_SECONDS=0,
        CHECK_RETRY_JITTER_MAX_SECONDS=0,
    )
    try:
        with session_factory() as db:
            target = Target(name="Screenshot retry limit", url="https://example.com")
            db.add(target)
            db.commit()
            target_id = target.id

        async def baseline_capture(url: str, current: Settings, out_dir: Path) -> CaptureResult:
            return make_capture(out_dir, "screenshot-limit-baseline", "Same page", "white")

        with session_factory() as db:
            target = db.get(Target, target_id)
            assert target is not None
            await run_target_check(db, target, settings, baseline_capture)
            approve_baseline(db, target_id, "screenshot-limit-baseline", settings)
            target = db.get(Target, target_id)
            assert target is not None
            target.check_run_id = "screenshot-limit-run"
            target.check_run_source = "scheduled"
            db.commit()

        async def failed_capture(url: str, current: Settings, out_dir: Path) -> CaptureResult:
            raise ScreenshotCaptureError(
                "Page.screenshot: Protocol error (Page.captureScreenshot): "
                "Unable to capture screenshot"
            )

        assert try_acquire_in_flight(target_id)
        await run_check_attempt(
            target_id,
            settings,
            run_id="screenshot-limit-run",
            initial_source="scheduled",
            capture_func=failed_capture,
            session_factory=session_factory,
        )
        with session_factory() as db:
            target = db.get(Target, target_id)
            assert target is not None and target.next_check_at is not None
            target.next_check_at = utcnow() - timedelta(seconds=1)
            db.commit()

        assert try_acquire_in_flight(target_id)
        result = await run_check_attempt(
            target_id,
            settings,
            run_id="screenshot-limit-run",
            initial_source="scheduled",
            capture_func=failed_capture,
            session_factory=session_factory,
        )
        assert result is not None and result.error_code == "screenshot_capture_failed"

        with session_factory() as db:
            target = db.get(Target, target_id)
            attempts = list(
                db.scalars(
                    select(CheckAttempt)
                    .where(CheckAttempt.run_id == "screenshot-limit-run")
                    .order_by(CheckAttempt.attempt_number)
                )
            )
            assert target is not None and target.check_run_id is None
            assert target.next_check_at is not None
            assert (target.next_check_at - utcnow()).total_seconds() >= 3590
            assert len(attempts) == 2
            assert all(item.error_code == "screenshot_capture_failed" for item in attempts)
    finally:
        engine.dispose()
