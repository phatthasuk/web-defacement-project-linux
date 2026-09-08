import asyncio
import logging
import shutil
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import SsrfBlockedError, ValidationError
from app.core.status import (
    STATUS_AVAILABILITY_ISSUE,
    STATUS_CHANGED,
    STATUS_CHECKING,
    STATUS_FAILED,
    STATUS_OK,
    require_valid_transition,
)
from app.models import CheckResult, Snapshot, Target
from app.services.capture.capture import CaptureResult, capture_snapshot
from app.services.diff import compare_snapshot_artifacts
from app.services.diff.diff import DiffResult

logger = logging.getLogger(__name__)

CaptureFunc = Callable[[str, Settings, Path], Awaitable[CaptureResult]]

STALE_CHECK_ERROR = "Check did not finish: the server restarted while this check was running."

# Stands in for a zero threshold so severities stay finite and comparable.
_ZERO_THRESHOLD_EPSILON = 1e-9


@dataclass(frozen=True)
class TargetCheckResult:
    status: str
    snapshot: Snapshot | None
    check_result: CheckResult | None
    target_id: str | None = None
    error: str | None = None
    skipped: bool = False


def is_availability_error(exc: Exception) -> bool:
    """Determine whether an error is transient availability failure vs a fatal bug.

    Stage 1.3: Timeouts, DNS failures, connection resets/refused are classified
    as Availability Issue rather than generic Failed. SSRF blocks are security
    violations, not availability issues.
    """
    if isinstance(exc, SsrfBlockedError):
        return False
    if isinstance(exc, TimeoutError):
        return True
    msg = str(exc).lower()
    if "blocked by ssrf guard" in msg:
        return False
    availability_indicators = (
        "timeout",
        "timed out",
        "name not resolved",
        "err_name_not_resolved",
        "connection refused",
        "err_connection_refused",
        "connection reset",
        "err_connection_reset",
        "connection timed out",
        "err_connection_timed_out",
        "host unreachable",
        "failed to resolve host",
        "network error",
        "gaierror",
    )
    return any(ind in msg for ind in availability_indicators)


def _promote_staging_artifacts(
    snapshot_id: str,
    staging_dir: Path | None,
    data_dir: Path,
    fallback_paths: tuple[str, str, str],
) -> tuple[str, str, str]:
    """Promote artifacts from staging to permanent storage directories.

    If staging_dir exists, moves files to data_dir/{screenshots,text,html}.
    If files were written directly (e.g. test fixtures), existing paths are preserved.
    """
    dest_screenshots = data_dir / "screenshots" / f"{snapshot_id}.png"
    dest_text = data_dir / "text" / f"{snapshot_id}.txt"
    dest_html = data_dir / "html" / f"{snapshot_id}.html"

    if staging_dir and staging_dir.is_dir():
        dest_screenshots.parent.mkdir(parents=True, exist_ok=True)
        dest_text.parent.mkdir(parents=True, exist_ok=True)
        dest_html.parent.mkdir(parents=True, exist_ok=True)

        staging_screenshot = staging_dir / f"{snapshot_id}.png"
        staging_text = staging_dir / f"{snapshot_id}.txt"
        staging_html = staging_dir / f"{snapshot_id}.html"

        if staging_screenshot.exists():
            shutil.move(str(staging_screenshot), str(dest_screenshots))
        if staging_text.exists():
            shutil.move(str(staging_text), str(dest_text))
        if staging_html.exists():
            shutil.move(str(staging_html), str(dest_html))

        shutil.rmtree(staging_dir, ignore_errors=True)
        return str(dest_screenshots), str(dest_text), str(dest_html)

    return fallback_paths


def _discard_snapshot_files(capture: CaptureResult) -> None:
    """Discard temporary capture artifacts.

    Stage 1.2: Unchanged checks consume 0 bytes of disk.
    Finding F5: Failed/aborted checks do not leave orphan artifacts.
    """
    staging_dir = Path(capture.staging_dir) if capture.staging_dir else None
    if staging_dir and staging_dir.is_dir():
        shutil.rmtree(staging_dir, ignore_errors=True)
        return

    # Fallback if artifacts were written directly outside staging (e.g. test fixtures)
    for p in (capture.screenshot_path, capture.text_path, capture.html_path):
        if p:
            try:
                Path(p).unlink(missing_ok=True)
            except OSError:
                pass


async def run_target_check(
    db: Session,
    target: Target,
    settings: Settings,
    capture_func: CaptureFunc = capture_snapshot,
) -> TargetCheckResult:
    transition_target(target, STATUS_CHECKING)
    target.last_error = None
    db.commit()

    try:
        capture = await capture_func(target.url, settings, settings.data_dir_path)
    except Exception as exc:
        target.last_error = str(exc)
        next_status = STATUS_AVAILABILITY_ISSUE if is_availability_error(exc) else STATUS_FAILED
        transition_target(target, next_status)
        db.commit()
        logger.warning(f"Capture failed for target {target.id}: {exc} (status={next_status})")
        return TargetCheckResult(
            status=next_status,
            snapshot=None,
            check_result=None,
            target_id=target.id,
            error=str(exc),
        )

    staging_dir = Path(capture.staging_dir) if capture.staging_dir else None

    # Check for HTTP 5xx responses -> Availability Issue (Stage 1.3)
    if capture.http_status is not None and capture.http_status >= 500:
        _discard_snapshot_files(capture)
        error_msg = f"Target returned HTTP {capture.http_status}"
        target.last_error = error_msg
        transition_target(target, STATUS_AVAILABILITY_ISSUE)
        db.commit()
        logger.warning(f"Target {target.id} returned HTTP {capture.http_status}")
        return TargetCheckResult(
            status=STATUS_AVAILABILITY_ISSUE,
            snapshot=None,
            check_result=None,
            target_id=target.id,
            error=error_msg,
        )

    try:
        baseline = get_baseline_snapshot(db, target.id)

        if baseline is None:
            # First snapshot: promote to baseline and retain permanently
            perm_screenshot, perm_text, perm_html = _promote_staging_artifacts(
                capture.id,
                staging_dir,
                settings.data_dir_path,
                (capture.screenshot_path, capture.text_path, capture.html_path),
            )
            snapshot = Snapshot(
                id=capture.id,
                target_id=target.id,
                final_url=capture.final_url,
                http_status=capture.http_status,
                title=capture.title,
                screenshot_path=perm_screenshot,
                text_path=perm_text,
                html_path=perm_html,
                is_baseline=True,
            )
            db.add(snapshot)
            transition_target(target, STATUS_OK)
            db.commit()
            db.refresh(snapshot)
            return TargetCheckResult(
                status=STATUS_OK,
                snapshot=snapshot,
                check_result=None,
                target_id=target.id,
            )

        # Compare against approved baselines using the staged files
        baselines = get_baseline_snapshots(db, target.id, settings.MAX_BASELINES_PER_TARGET)
        if not baselines:
            baselines = [baseline]
        baseline_artifacts = [
            BaselineArtifacts(
                snapshot_id=b.id,
                text_path=b.text_path,
                screenshot_path=b.screenshot_path,
                html_path=b.html_path,
                final_url=b.final_url,
            )
            for b in baselines
        ]
        allowed_hosts = tuple(target.allowed_domains or ())

        # Diffing is CPU-bound (image comparison); run it off the event loop so it does
        # not stall other concurrent checks sharing this loop.
        comparisons = await asyncio.to_thread(
            _diff_against_baselines,
            baseline_artifacts,
            capture.text_path,
            capture.screenshot_path,
            capture.html_path,
            capture.final_url,
            allowed_hosts,
        )
        matched_baseline_id, diff = select_best_baseline(comparisons, settings)
        has_changes = diff_severity(diff, settings) > 1.0

        if len(comparisons) > 1:
            logger.debug(
                "Target %s matched baseline %s out of %d (text=%.6f visual=%.6f)",
                target.id,
                matched_baseline_id,
                len(comparisons),
                diff.text_change_score,
                diff.visual_change_score,
            )

        if has_changes:
            # Genuine change: promote staged artifacts to permanent storage
            perm_screenshot, perm_text, perm_html = _promote_staging_artifacts(
                capture.id,
                staging_dir,
                settings.data_dir_path,
                (capture.screenshot_path, capture.text_path, capture.html_path),
            )
            snapshot = Snapshot(
                id=capture.id,
                target_id=target.id,
                final_url=capture.final_url,
                http_status=capture.http_status,
                title=capture.title,
                screenshot_path=perm_screenshot,
                text_path=perm_text,
                html_path=perm_html,
                is_baseline=False,
            )
            db.add(snapshot)
            check_result = CheckResult(
                target_id=target.id,
                baseline_snapshot_id=matched_baseline_id,
                current_snapshot_id=snapshot.id,
                status=STATUS_CHANGED,
                text_change_score=diff.text_change_score,
                visual_change_score=diff.visual_change_score,
                structure_change_score=diff.structure_change_score,
                summary=diff.summary,
            )
            transition_target(target, STATUS_CHANGED)
            db.add(check_result)
            db.commit()
            db.refresh(snapshot)
            db.refresh(check_result)
            return TargetCheckResult(
                status=STATUS_CHANGED,
                snapshot=snapshot,
                check_result=check_result,
                target_id=target.id,
            )
        else:
            # Unchanged check (Stage 1.2): discard staging artifacts, leaving 0 bytes on disk!
            _discard_snapshot_files(capture)
            matched_baseline = db.get(Snapshot, matched_baseline_id) or baseline
            check_result = CheckResult(
                target_id=target.id,
                baseline_snapshot_id=matched_baseline_id,
                current_snapshot_id=matched_baseline_id,
                status=STATUS_OK,
                text_change_score=diff.text_change_score,
                visual_change_score=diff.visual_change_score,
                structure_change_score=diff.structure_change_score,
                summary=diff.summary,
            )
            transition_target(target, STATUS_OK)
            db.add(check_result)
            db.commit()
            db.refresh(check_result)
            return TargetCheckResult(
                status=STATUS_OK,
                snapshot=matched_baseline,
                check_result=check_result,
                target_id=target.id,
            )
    except Exception as exc:
        # F5: Discard staging files on diff or commit failure so no orphans remain
        _discard_snapshot_files(capture)
        target.last_error = str(exc)
        next_status = STATUS_AVAILABILITY_ISSUE if is_availability_error(exc) else STATUS_FAILED
        transition_target(target, next_status)
        db.commit()
        logger.exception("Error checking target %s: %s", target.id, exc)
        return TargetCheckResult(
            status=next_status,
            snapshot=None,
            check_result=None,
            target_id=target.id,
            error=str(exc),
        )


def recover_stale_checks(db: Session) -> list[str]:
    """Release targets left in `Checking` by a process that no longer exists.

    Checks run in-process via FastAPI ``BackgroundTasks``, and `run_target_check`
    commits `Checking` before capture starts. If the process dies in that window
    the job is gone for good, but the row still says `Checking` — and
    `trigger_target_check` refuses to start a new check for such a target, so it
    can never be checked again without editing the database by hand.

    Any target still `Checking` at startup therefore belongs to a dead process:
    this run has not scheduled anything yet. Mark those `Failed` so they become
    eligible for a retry.

    NOTE: this assumes a single API worker, which `app.services.concurrency`
    already requires for its process-local concurrency caps. With several
    workers, a starting worker would wrongly fail checks still running in a
    sibling worker; a durable queue with per-job leases is the fix there (see
    plan/PROJECT_PLAN.md, finding F8).

    Returns the ids of the targets that were released.
    """
    stale_targets = list(db.scalars(select(Target).where(Target.status == STATUS_CHECKING)))
    if not stale_targets:
        return []

    for target in stale_targets:
        target.last_error = STALE_CHECK_ERROR
        transition_target(target, STATUS_FAILED)
    db.commit()

    released_ids = [target.id for target in stale_targets]
    logger.warning(
        "Released %d target(s) stuck in %s after an unclean shutdown: %s",
        len(released_ids),
        STATUS_CHECKING,
        ", ".join(released_ids),
    )
    return released_ids


def get_baseline_snapshot(db: Session, target_id: str) -> Snapshot | None:
    """The newest approved baseline, for display and for "does one exist" checks."""
    return db.scalar(
        select(Snapshot)
        .where(Snapshot.target_id == target_id, Snapshot.is_baseline.is_(True))
        .order_by(Snapshot.captured_at.desc(), Snapshot.id.desc())
    )


def get_baseline_snapshots(db: Session, target_id: str, limit: int) -> list[Snapshot]:
    """Every approved baseline for a target, newest first."""
    if limit <= 0:
        return []
    return list(
        db.scalars(
            select(Snapshot)
            .where(Snapshot.target_id == target_id, Snapshot.is_baseline.is_(True))
            .order_by(Snapshot.captured_at.desc(), Snapshot.id.desc())
            .limit(limit)
        )
    )


def prune_baselines(db: Session, target_id: str, keep: int) -> list[str]:
    """Demote all but the `keep` newest baselines. Returns the demoted ids.

    Only the `is_baseline` flag is cleared: the snapshots and their artifacts
    stay, so history and any CheckResult referencing them remain intact.
    """
    if keep < 1:
        raise ValidationError(f"Baseline keep cap must be at least 1, got {keep}")
    baselines = list(
        db.scalars(
            select(Snapshot)
            .where(Snapshot.target_id == target_id, Snapshot.is_baseline.is_(True))
            .order_by(Snapshot.captured_at.desc(), Snapshot.id.desc())
        )
    )
    demoted = baselines[max(keep, 0) :]
    for snapshot in demoted:
        snapshot.is_baseline = False
    if demoted:
        db.flush()
    return [snapshot.id for snapshot in demoted]


def _threshold_ratio(score: float, threshold: float) -> float:
    """Score expressed as a multiple of its threshold; >1 means it is exceeded.

    A threshold of zero means zero tolerance, but returning infinity there would
    make every affected baseline rank equally and destroy `select_best_baseline`'s
    ordering. Dividing by a tiny epsilon keeps the ">1 means exceeded" contract
    while still ordering a small change ahead of a large one.
    """
    if threshold > 0:
        return score / threshold
    if score <= 0:
        return 0.0
    return score / _ZERO_THRESHOLD_EPSILON


def diff_severity(diff: DiffResult, settings: Settings) -> float:
    """How close a diff is to being reported, across every detector.

    Normalising each score by its own threshold makes them comparable, so a
    single number can both decide the outcome and rank baselines. `severity > 1`
    is exactly the "some score exceeds its threshold" condition.
    """
    return max(
        _threshold_ratio(diff.text_change_score, settings.TEXT_CHANGE_THRESHOLD),
        _threshold_ratio(diff.visual_change_score, settings.VISUAL_CHANGE_THRESHOLD),
        _threshold_ratio(diff.structure_change_score, settings.STRUCTURE_CHANGE_THRESHOLD),
    )


def select_best_baseline(
    comparisons: list[tuple[str, DiffResult]],
    settings: Settings,
) -> tuple[str, DiffResult]:
    """Pick the baseline the current snapshot resembles most.

    The lowest severity wins, which also means a matching baseline is preferred
    whenever one exists: matching is `severity <= 1` and every non-match scores
    above that. So a page is only reported as Changed when it differs from
    *every* known-good baseline.
    """
    if not comparisons:
        raise ValueError("select_best_baseline requires at least one comparison")
    return min(comparisons, key=lambda item: diff_severity(item[1], settings))


@dataclass(frozen=True)
class BaselineArtifacts:
    """Paths and metadata for one baseline, detached from the ORM.

    `_diff_against_baselines` runs in a worker thread, where touching a
    Session-bound instance is not safe, so everything it needs is copied here
    on the event loop first.
    """

    snapshot_id: str
    text_path: str
    screenshot_path: str
    html_path: str
    final_url: str


def _diff_against_baselines(
    baselines: list[BaselineArtifacts],
    current_text_path: str,
    current_screenshot_path: str,
    current_html_path: str,
    current_url: str,
    allowed_hosts: tuple[str, ...],
) -> list[tuple[str, DiffResult]]:
    """Diff one snapshot against several baselines."""
    return [
        (
            baseline.snapshot_id,
            compare_snapshot_artifacts(
                baseline_text_path=baseline.text_path,
                current_text_path=current_text_path,
                baseline_screenshot_path=baseline.screenshot_path,
                current_screenshot_path=current_screenshot_path,
                baseline_html_path=baseline.html_path,
                current_html_path=current_html_path,
                baseline_url=baseline.final_url,
                current_url=current_url,
                allowed_hosts=allowed_hosts,
            ),
        )
        for baseline in baselines
    ]


def transition_target(target: Target, next_status: str) -> None:
    require_valid_transition(target.status, next_status)
    target.status = next_status


def reconcile_artifacts(db: Session, settings: Settings) -> dict[str, int]:
    """Clean up expired staging directories and orphan artifact files.

    Fulfills Finding F5 and Section 9.3:
    - Removes staging directories older than STAGING_CLEANUP_MAX_AGE_SECONDS.
    - Removes files in screenshots/, text/, html/ that have no matching Snapshot in DB.
    - Ensures every deletion is strictly within settings.data_dir_path.
    """
    cleaned_staging = 0
    cleaned_orphans = 0
    data_dir = settings.data_dir_path.resolve()

    # 1. Clean expired staging directories
    staging_root = data_dir / "staging"
    if staging_root.is_dir():
        now = time.time()
        for item in staging_root.iterdir():
            if item.is_dir():
                try:
                    if not item.resolve().is_relative_to(data_dir):
                        continue
                    age = now - item.stat().st_mtime
                    if age > settings.STAGING_CLEANUP_MAX_AGE_SECONDS:
                        shutil.rmtree(item, ignore_errors=True)
                        cleaned_staging += 1
                except OSError:
                    pass

    # 2. Clean orphan artifact files in permanent storage
    valid_ids = set(db.scalars(select(Snapshot.id)))
    for subdir_name in ("screenshots", "text", "html"):
        sub_dir = data_dir / subdir_name
        if not sub_dir.is_dir():
            continue
        for file_path in sub_dir.iterdir():
            if file_path.is_file():
                try:
                    if not file_path.resolve().is_relative_to(data_dir):
                        continue
                    snapshot_id = file_path.stem
                    if snapshot_id not in valid_ids:
                        file_path.unlink(missing_ok=True)
                        cleaned_orphans += 1
                except OSError:
                    pass

    if cleaned_staging > 0 or cleaned_orphans > 0:
        logger.info(
            "Reconciliation complete: removed %d expired staging dirs, %d orphan artifact files",
            cleaned_staging,
            cleaned_orphans,
        )

    return {"cleaned_staging": cleaned_staging, "cleaned_orphans": cleaned_orphans}
