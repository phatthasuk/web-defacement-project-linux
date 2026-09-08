import asyncio
import logging
from collections.abc import Callable
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.status import (
    STATUS_AVAILABILITY_ISSUE,
    STATUS_CHECKING,
    STATUS_FAILED,
    is_valid_transition,
)
from app.db.session import SessionLocal
from app.models import Target
from app.services.capture.capture import capture_snapshot
from app.services.checks import (
    CaptureFunc,
    TargetCheckResult,
    is_availability_error,
    run_target_check,
)

logger = logging.getLogger(__name__)

RESULT_SKIPPED = "Skipped"
RESULT_NOT_FOUND = "Not Found"

SessionFactory = Callable[[], Session]

# NOTE: These caps and the in-flight de-dup set are process-local. Running
# uvicorn with multiple workers multiplies the effective concurrency limits
# and defeats duplicate-check suppression. Run a single worker, or move this
# state to the DB/Redis before scaling out.
_global_semaphore: asyncio.Semaphore | None = None
_global_semaphore_loop: asyncio.AbstractEventLoop | None = None
_domain_semaphores: dict[str, asyncio.Semaphore] = {}
_domain_semaphores_loop: asyncio.AbstractEventLoop | None = None
_active_domain_counts: dict[str, int] = {}
_in_flight_targets: set[str] = set()

def get_global_semaphore(limit: int) -> asyncio.Semaphore:
    global _global_semaphore, _global_semaphore_loop
    current_loop = asyncio.get_running_loop()
    if _global_semaphore is None or _global_semaphore_loop != current_loop:
        _global_semaphore = asyncio.Semaphore(limit)
        _global_semaphore_loop = current_loop
    return _global_semaphore

def get_domain_semaphore(domain: str, limit: int) -> asyncio.Semaphore:
    global _domain_semaphores, _domain_semaphores_loop
    current_loop = asyncio.get_running_loop()
    if _domain_semaphores_loop != current_loop:
        _domain_semaphores.clear()
        _domain_semaphores_loop = current_loop
    
    if domain not in _domain_semaphores:
        _domain_semaphores[domain] = asyncio.Semaphore(limit)
    return _domain_semaphores[domain]

def is_target_in_flight(target_id: str) -> bool:
    return target_id in _in_flight_targets

async def run_checks_for_targets(
    target_ids: list[str],
    settings: Settings,
    capture_func: CaptureFunc = capture_snapshot,
    session_factory: SessionFactory = SessionLocal,
    timeout_seconds: float | None = None,
) -> list[TargetCheckResult]:
    domain_keys = load_domain_keys(target_ids, session_factory)
    timeout = (
        timeout_seconds
        if timeout_seconds is not None
        else float(settings.CHECK_TIMEOUT_SECONDS)
    )

    async def worker(target_id: str) -> TargetCheckResult:
        if target_id in _in_flight_targets:
            return TargetCheckResult(
                status=RESULT_SKIPPED,
                snapshot=None,
                check_result=None,
                target_id=target_id,
                error="Target check is already in progress",
                skipped=True,
            )
        _in_flight_targets.add(target_id)

        domain_key = domain_keys.get(target_id, fallback_domain_key(target_id))
        _active_domain_counts[domain_key] = _active_domain_counts.get(domain_key, 0) + 1
        domain_semaphore = get_domain_semaphore(domain_key, settings.PER_DOMAIN_CONCURRENCY)
        global_semaphore = get_global_semaphore(settings.MAX_CONCURRENT_CHECKS)

        try:
            with session_factory() as db:
                target = db.get(Target, target_id)
                if target is None:
                    return TargetCheckResult(
                        status=RESULT_NOT_FOUND,
                        snapshot=None,
                        check_result=None,
                        target_id=target_id,
                        error="Target not found",
                        skipped=True,
                    )
                if not target.is_active:
                    return TargetCheckResult(
                        status=RESULT_SKIPPED,
                        snapshot=None,
                        check_result=None,
                        target_id=target_id,
                        error="Target is inactive",
                        skipped=True,
                    )
                if target.status == STATUS_CHECKING:
                    return TargetCheckResult(
                        status=RESULT_SKIPPED,
                        snapshot=None,
                        check_result=None,
                        target_id=target_id,
                        skipped=True,
                    )

            async with global_semaphore:
                async with domain_semaphore:
                    with session_factory() as db:
                        target = db.get(Target, target_id)
                        if target is None:
                            return TargetCheckResult(
                                status=RESULT_NOT_FOUND,
                                snapshot=None,
                                check_result=None,
                                target_id=target_id,
                                error="Target not found",
                                skipped=True,
                            )
                        if not target.is_active:
                            return TargetCheckResult(
                                status=RESULT_SKIPPED,
                                snapshot=None,
                                check_result=None,
                                target_id=target_id,
                                error="Target is inactive",
                                skipped=True,
                            )
                        if target.status == STATUS_CHECKING:
                            return TargetCheckResult(
                                status=RESULT_SKIPPED,
                                snapshot=None,
                                check_result=None,
                                target_id=target_id,
                                skipped=True,
                            )
                        try:
                            return await asyncio.wait_for(
                                run_target_check(db, target, settings, capture_func=capture_func),
                                timeout=timeout,
                            )
                        except TimeoutError:
                            error_msg = f"Check timed out after {timeout:.2f} seconds"
                            logger.warning(f"Timeout checking target {target_id}: {error_msg}")
                            mark_target_status(
                                db, target_id, STATUS_AVAILABILITY_ISSUE, error=error_msg
                            )
                            return TargetCheckResult(
                                status=STATUS_AVAILABILITY_ISSUE,
                                snapshot=None,
                                check_result=None,
                                target_id=target_id,
                                error=error_msg,
                            )
                        except Exception as exc:
                            error_msg = str(exc)
                            logger.exception(
                                "Unexpected error checking target %s: %s",
                                target_id,
                                error_msg,
                            )
                            err_status = (
                                STATUS_AVAILABILITY_ISSUE
                                if is_availability_error(exc)
                                else STATUS_FAILED
                            )
                            mark_target_status(db, target_id, err_status, error=error_msg)
                            return TargetCheckResult(
                                status=err_status,
                                snapshot=None,
                                check_result=None,
                                target_id=target_id,
                                error=error_msg,
                            )
        finally:
            _in_flight_targets.discard(target_id)
            _active_domain_counts[domain_key] -= 1
            if _active_domain_counts[domain_key] <= 0:
                _active_domain_counts.pop(domain_key, None)
                _domain_semaphores.pop(domain_key, None)

    results = await asyncio.gather(
        *(worker(target_id) for target_id in target_ids),
        return_exceptions=True,
    )

    final_results: list[TargetCheckResult] = []
    for target_id, res in zip(target_ids, results, strict=False):
        if isinstance(res, BaseException):
            error_msg = f"Worker crashed: {res}"
            logger.error(error_msg, exc_info=res)
            with session_factory() as db:
                mark_target_failed(db, target_id, error=error_msg)
            final_results.append(
                TargetCheckResult(
                    status=STATUS_FAILED,
                    snapshot=None,
                    check_result=None,
                    target_id=target_id,
                    error=error_msg,
                )
            )
        else:
            final_results.append(res)
    return final_results


def load_domain_keys(target_ids: list[str], session_factory: SessionFactory) -> dict[str, str]:
    unique_target_ids = list(dict.fromkeys(target_ids))
    if not unique_target_ids:
        return {}

    with session_factory() as db:
        targets = db.scalars(select(Target).where(Target.id.in_(unique_target_ids)))
        return {target.id: domain_key_for_target(target) for target in targets}


def domain_key_for_target(target: Target) -> str:
    hostname = urlparse(target.url).hostname
    if hostname:
        return hostname.lower()
    return fallback_domain_key(target.id)


def fallback_domain_key(target_id: str) -> str:
    return f"target:{target_id}"


def mark_target_status(
    db: Session,
    target_id: str,
    status: str,
    error: str | None = None,
) -> None:
    db.rollback()
    target = db.get(Target, target_id)
    if target is None:
        return
    target.last_error = error
    if is_valid_transition(target.status, status):
        target.status = status
    else:
        logger.warning(
            "Skipping status transition %r -> %r for target %s", target.status, status, target_id
        )
    db.commit()


def mark_target_failed(db: Session, target_id: str, error: str | None = None) -> None:
    mark_target_status(db, target_id, STATUS_FAILED, error=error)
