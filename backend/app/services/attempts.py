"""Run and persist one attempt, then schedule its retry or next hourly check."""

import logging
import random
from datetime import timedelta

from app.core.config import Settings
from app.core.time import utcnow
from app.db.session import SessionLocal
from app.models import CheckAttempt, Target
from app.services.checks import CaptureFunc, TargetCheckResult
from app.services.concurrency import SessionFactory, release_in_flight, run_checks_for_targets

logger = logging.getLogger("app.attempts")


def _recover_attempt_finalization_failure(
    *,
    target_id: str,
    run_id: str,
    url_revision: int | None,
    attempt_id: str,
    result: TargetCheckResult,
    error: Exception,
    settings: Settings,
    session_factory: SessionFactory,
) -> None:
    """Best-effort recovery after result recording failed in its own transaction."""
    try:
        with session_factory() as db:
            attempt = db.get(CheckAttempt, attempt_id)
            target = db.get(Target, target_id)
            finished_at = utcnow()

            if attempt is not None and attempt.finished_at is None:
                attempt.finished_at = finished_at
                attempt.status = result.status
                attempt.error_code = "attempt_persistence_error"
                detail = f"Attempt finalization failed: {error}"
                if result.error:
                    detail = f"{detail}; check result: {result.error}"
                attempt.error_message = detail
                attempt.http_status = result.http_status
                attempt.check_result_id = result.check_result_id
                attempt.snapshot_id = result.snapshot_id

            if (
                target is not None
                and target.check_run_id == run_id
                and target.url_revision == url_revision
                and target.next_check_at is None
            ):
                jitter = random.uniform(0, settings.CHECK_JITTER_MAX_SECONDS)
                target.next_check_at = finished_at + timedelta(
                    seconds=settings.CHECK_INTERVAL_SECONDS + jitter
                )
                target.check_run_id = None
                target.check_run_source = None
                target.check_attempt_count = 0

            db.commit()
    except Exception:
        logger.exception(
            "Could not recover failed attempt finalization target=%s run=%s; original error: %s",
            target_id,
            run_id,
            error,
        )


def _is_retryable(error_code: str | None) -> bool:
    if error_code in {
        "check_timeout",
        "capture_timeout",
        "dns_resolution",
        "upstream_connection",
        "network_unavailable",
        "no_http_response",
    }:
        return True
    return error_code in {"http_408", "http_429", "http_500", "http_502", "http_503", "http_504"}


async def run_check_attempt(
    target_id: str,
    settings: Settings,
    *,
    run_id: str,
    initial_source: str,
    capture_func: CaptureFunc,
    session_factory: SessionFactory = SessionLocal,
    actor_id: int | None = None,
) -> TargetCheckResult | None:
    """Execute exactly one durable attempt for an already reserved target."""
    attempt_id: str | None = None
    url_revision: int | None = None
    attempt_number = 0
    try:
        with session_factory() as db:
            target = db.get(Target, target_id)
            if target is None or not target.is_active or target.check_run_id != run_id:
                return None
            url_revision = target.url_revision
            target.check_attempt_count += 1
            attempt_number = target.check_attempt_count
            source = initial_source if attempt_number == 1 else "retry"
            target.next_check_at = None
            attempt = CheckAttempt(
                target_id=target.id,
                url_revision=url_revision,
                run_id=run_id,
                attempt_number=attempt_number,
                source=source,
                actor_id=actor_id if attempt_number == 1 else None,
                started_at=utcnow(),
                status="Checking",
            )
            db.add(attempt)
            db.commit()
            attempt_id = attempt.id

        try:
            results = await run_checks_for_targets(
                [target_id],
                settings,
                capture_func=capture_func,
                session_factory=session_factory,
                pre_reserved=True,
            )
            result = results[0]
        except Exception as exc:
            logger.exception("Check attempt crashed for target %s", target_id)
            result = TargetCheckResult(
                status="Failed",
                snapshot=None,
                check_result=None,
                target_id=target_id,
                error=str(exc),
                error_code="internal_error",
            )

        finished_at = utcnow()
        try:
            with session_factory() as db:
                attempt = db.get(CheckAttempt, attempt_id)
                target = db.get(Target, target_id)
                if attempt is None or target is None:
                    raise RuntimeError(
                        f"Attempt or target disappeared during finalization: {attempt_id}"
                    )
                attempt.finished_at = finished_at
                attempt.status = result.status
                attempt.error_code = result.error_code
                attempt.error_message = result.error
                attempt.http_status = result.http_status
                attempt.check_result_id = result.check_result_id
                attempt.snapshot_id = result.snapshot_id

                # Do not let a stale run rewrite the schedule after a URL revision
                # or a newer manual run has taken ownership.
                if target.check_run_id == run_id and target.url_revision == url_revision:
                    retryable = _is_retryable(result.error_code)
                    retry_limit = settings.CHECK_RETRY_MAX_ATTEMPTS
                    delays = settings.check_retry_delays_list
                    if (
                        result.error_code
                        and settings.CHECK_RETRY_ENABLED
                        and retryable
                        and attempt_number < retry_limit
                        and attempt_number <= len(delays)
                    ):
                        delay = delays[attempt_number - 1] + random.uniform(
                            0, settings.CHECK_RETRY_JITTER_MAX_SECONDS
                        )
                        if result.retry_after_seconds is not None:
                            delay = max(
                                delay,
                                min(
                                    result.retry_after_seconds,
                                    settings.CHECK_RETRY_AFTER_MAX_SECONDS,
                                ),
                            )
                        target.next_check_at = finished_at + timedelta(seconds=delay)
                        logger.info(
                            "Retry scheduled target=%s attempt=%d/%d due=%s error=%s",
                            target_id,
                            attempt_number + 1,
                            retry_limit,
                            target.next_check_at.isoformat(),
                            result.error_code,
                        )
                    else:
                        jitter = random.uniform(0, settings.CHECK_JITTER_MAX_SECONDS)
                        target.next_check_at = finished_at + timedelta(
                            seconds=settings.CHECK_INTERVAL_SECONDS + jitter
                        )
                        target.check_run_id = None
                        target.check_run_source = None
                        target.check_attempt_count = 0
                db.commit()
        except Exception as exc:
            logger.exception("Could not finalize check attempt for target %s", target_id)
            _recover_attempt_finalization_failure(
                target_id=target_id,
                run_id=run_id,
                url_revision=url_revision,
                attempt_id=attempt_id,
                result=result,
                error=exc,
                settings=settings,
                session_factory=session_factory,
            )
        return result
    finally:
        # run_checks_for_targets also releases this reservation on normal paths;
        # discard is idempotent and covers failures before it is entered.
        release_in_flight(target_id)
        if attempt_id is None:
            # If durable attempt creation itself failed, avoid leaving an
            # un-runnable run with a null deadline until the next restart.
            with session_factory() as db:
                target = db.get(Target, target_id)
                if target is not None and target.check_run_id == run_id and target.next_check_at is None:
                    target.next_check_at = utcnow() + timedelta(seconds=60)
                    db.commit()
