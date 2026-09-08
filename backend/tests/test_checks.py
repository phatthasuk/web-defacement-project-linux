import math
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from PIL import Image
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.errors import SsrfBlockedError
from app.core.status import (
    STATUS_AVAILABILITY_ISSUE,
    STATUS_CHANGED,
    STATUS_CHECKING,
    STATUS_FAILED,
    STATUS_NEVER_CHECKED,
    STATUS_OK,
)
from app.db.session import Base
from app.models import CheckResult, Snapshot, Target
from app.services.capture.capture import CaptureResult
from app.services.checks import (
    STALE_CHECK_ERROR,
    diff_severity,
    reconcile_artifacts,
    recover_stale_checks,
    run_target_check,
    select_best_baseline,
)
from app.services.diff.diff import DiffResult
from app.services.review import acknowledge_check_result


def make_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session_local = sessionmaker(bind=engine)
    return session_local()


async def test_run_target_check_marks_first_snapshot_as_baseline(tmp_path: Path):
    work_dir = make_work_dir("checks-baseline", tmp_path)
    db = make_session()
    target = Target(name="Example", url="https://example.com")
    db.add(target)
    db.commit()
    db.refresh(target)

    async def fake_capture(url: str, settings: Settings, out_dir: Path) -> CaptureResult:
        return write_capture(out_dir, "first", "Hello", "white")

    result = await run_target_check(
        db,
        target,
        Settings(DATA_DIR=str(work_dir)),
        capture_func=fake_capture,
    )

    assert result.check_result is None
    assert result.snapshot is not None
    assert result.snapshot.is_baseline is True
    assert result.status == STATUS_OK
    assert target.status == STATUS_OK


async def test_run_target_check_stores_check_result_against_baseline(tmp_path: Path):
    work_dir = make_work_dir("checks-result", tmp_path)
    db = make_session()
    target = Target(name="Example", url="https://example.com")
    db.add(target)
    db.commit()
    db.refresh(target)

    captures = [
        write_capture(work_dir, "baseline", "Hello", "white"),
        write_capture(work_dir, "current", "Changed", "black"),
    ]

    async def fake_capture(url: str, settings: Settings, out_dir: Path) -> CaptureResult:
        return captures.pop(0)

    settings = Settings(DATA_DIR=str(work_dir))
    await run_target_check(db, target, settings, capture_func=fake_capture)
    result = await run_target_check(db, target, settings, capture_func=fake_capture)

    persisted_checks = list(db.scalars(select(CheckResult)))
    snapshots = list(db.scalars(select(Snapshot)))

    assert result.check_result is not None
    assert result.check_result.status == "Changed"
    assert result.snapshot is not None
    assert result.status == STATUS_CHANGED
    assert result.check_result.text_change_score > 0.0
    assert result.check_result.visual_change_score == 1.0
    assert len(persisted_checks) == 1
    assert len(snapshots) == 2
    assert sum(snapshot.is_baseline for snapshot in snapshots) == 1
    assert target.status == STATUS_CHANGED


async def test_run_target_check_marks_failed_without_snapshot_on_capture_error(tmp_path: Path):
    work_dir = make_work_dir("checks-failed", tmp_path)
    db = make_session()
    target = Target(name="Example", url="https://example.com")
    db.add(target)
    db.commit()
    db.refresh(target)

    async def fake_capture(url: str, settings: Settings, out_dir: Path) -> CaptureResult:
        raise RuntimeError("capture failed")

    result = await run_target_check(
        db,
        target,
        Settings(DATA_DIR=str(work_dir)),
        capture_func=fake_capture,
    )

    assert result.status == STATUS_FAILED
    assert result.snapshot is None
    assert result.check_result is None
    assert result.error == "capture failed"
    assert target.status == STATUS_FAILED
    assert list(db.scalars(select(Snapshot))) == []


async def test_run_target_check_reports_ssrf_block_as_failed(tmp_path: Path):
    work_dir = make_work_dir("checks-ssrf", tmp_path)
    db = make_session()
    target = Target(name="Example", url="http://169.254.169.254")
    db.add(target)
    db.commit()
    db.refresh(target)

    async def fake_capture(url: str, settings: Settings, out_dir: Path) -> CaptureResult:
        raise SsrfBlockedError("Blocked by SSRF guard: metadata address")

    result = await run_target_check(
        db,
        target,
        Settings(DATA_DIR=str(work_dir)),
        capture_func=fake_capture,
    )

    assert result.status == STATUS_FAILED
    assert result.error == "Blocked by SSRF guard: metadata address"
    assert target.status == STATUS_FAILED


async def test_run_target_check_commits_checking_before_capture(tmp_path: Path):
    work_dir = make_work_dir("checks-checking", tmp_path)
    db = make_session()
    target = Target(name="Example", url="https://example.com")
    db.add(target)
    db.commit()
    db.refresh(target)

    async def fake_capture(url: str, settings: Settings, out_dir: Path) -> CaptureResult:
        persisted_target = db.get(Target, target.id)
        assert persisted_target is not None
        assert persisted_target.status == STATUS_CHECKING
        return write_capture(out_dir, "first", "Hello", "white")

    await run_target_check(
        db,
        target,
        Settings(DATA_DIR=str(work_dir)),
        capture_func=fake_capture,
    )


async def test_run_target_check_rechecks_changed_after_acknowledgment(tmp_path: Path):
    work_dir = make_work_dir("checks-after-ack", tmp_path)
    db = make_session()
    target = Target(name="Example", url="https://example.com")
    db.add(target)
    db.commit()
    db.refresh(target)

    captures = [
        write_capture(work_dir, "baseline", "Hello", "white"),
        write_capture(work_dir, "changed-1", "Changed once", "black"),
        write_capture(work_dir, "changed-2", "Changed twice", "black"),
    ]

    async def fake_capture(url: str, settings: Settings, out_dir: Path) -> CaptureResult:
        return captures.pop(0)

    settings = Settings(DATA_DIR=str(work_dir))
    await run_target_check(db, target, settings, capture_func=fake_capture)
    changed_result = await run_target_check(db, target, settings, capture_func=fake_capture)
    assert changed_result.check_result is not None

    acknowledge_check_result(db, changed_result.check_result.id)
    assert target.status == "Acknowledged"

    next_result = await run_target_check(db, target, settings, capture_func=fake_capture)

    assert next_result.status == STATUS_CHANGED
    assert target.status == STATUS_CHANGED


async def test_run_target_check_treats_sub_threshold_diff_as_ok(tmp_path: Path):
    work_dir = make_work_dir("checks-threshold", tmp_path)
    db = make_session()
    target = Target(name="Example", url="https://example.com")
    db.add(target)
    db.commit()
    db.refresh(target)

    captures = [
        write_capture_sized(work_dir, "baseline", "The quick brown fox", changed_pixels=0),
        # One character of text changes and one pixel out of 100 changes, both well
        # below the thresholds configured below, so the check must resolve to OK.
        write_capture_sized(work_dir, "current", "The quick brown fps", changed_pixels=1),
    ]

    async def fake_capture(url: str, settings: Settings, out_dir: Path) -> CaptureResult:
        return captures.pop(0)

    settings = Settings(
        DATA_DIR=str(work_dir),
        TEXT_CHANGE_THRESHOLD=0.5,
        VISUAL_CHANGE_THRESHOLD=0.05,
    )
    await run_target_check(db, target, settings, capture_func=fake_capture)
    result = await run_target_check(db, target, settings, capture_func=fake_capture)

    assert result.status == STATUS_OK
    assert result.check_result is not None
    assert result.check_result.status == STATUS_OK
    assert 0.0 < result.check_result.visual_change_score <= 0.05
    assert target.status == STATUS_OK


def make_work_dir(prefix: str, tmp_path: Path) -> Path:
    work_dir = tmp_path / f"{prefix}-{uuid4()}"
    work_dir.mkdir(parents=True, exist_ok=True)
    return work_dir


def write_capture(out_dir: Path, snapshot_id: str, text: str, color: str) -> CaptureResult:
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


def write_capture_sized(
    out_dir: Path,
    snapshot_id: str,
    text: str,
    changed_pixels: int,
) -> CaptureResult:
    """Capture with a 10x10 white screenshot where ``changed_pixels`` are darkened.

    Lets a test dial the visual diff score in 1% steps (one pixel out of 100).
    """
    screenshot_path = out_dir / "screenshots" / f"{snapshot_id}.png"
    text_path = out_dir / "text" / f"{snapshot_id}.txt"
    html_path = out_dir / "html" / f"{snapshot_id}.html"

    screenshot_path.parent.mkdir(parents=True, exist_ok=True)
    text_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.parent.mkdir(parents=True, exist_ok=True)

    image = Image.new("RGB", (10, 10), "white")
    for index in range(changed_pixels):
        image.putpixel((index % 10, index // 10), (0, 0, 0))
    image.save(screenshot_path)
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


# --- Stale-check recovery after an unclean shutdown (Finding 8) ---


def test_recover_stale_checks_releases_targets_stuck_in_checking():
    db = make_session()
    stuck = Target(name="Stuck", url="https://stuck.example.com", status=STATUS_CHECKING)
    db.add(stuck)
    db.commit()
    db.refresh(stuck)

    released = recover_stale_checks(db)

    assert released == [stuck.id]
    db.refresh(stuck)
    assert stuck.status == STATUS_FAILED
    assert stuck.last_error == STALE_CHECK_ERROR


def test_recover_stale_checks_leaves_other_statuses_untouched():
    db = make_session()
    ok = Target(name="Ok", url="https://ok.example.com", status=STATUS_OK)
    changed = Target(name="Changed", url="https://changed.example.com", status=STATUS_CHANGED)
    never = Target(name="Never", url="https://never.example.com")
    db.add_all([ok, changed, never])
    db.commit()

    assert recover_stale_checks(db) == []

    for target in (ok, changed, never):
        db.refresh(target)
    assert ok.status == STATUS_OK
    assert changed.status == STATUS_CHANGED
    assert never.status == STATUS_NEVER_CHECKED
    assert ok.last_error is None


def test_recover_stale_checks_releases_every_stuck_target():
    db = make_session()
    stuck = [
        Target(
            name=f"Stuck {index}",
            url=f"https://stuck{index}.example.com",
            status=STATUS_CHECKING,
        )
        for index in range(3)
    ]
    healthy = Target(name="Healthy", url="https://healthy.example.com", status=STATUS_OK)
    db.add_all([*stuck, healthy])
    db.commit()

    released = recover_stale_checks(db)

    assert sorted(released) == sorted(target.id for target in stuck)
    assert all(
        db.scalar(select(Target.status).where(Target.id == target.id)) == STATUS_FAILED
        for target in stuck
    )


def test_recover_stale_checks_is_idempotent():
    db = make_session()
    db.add(Target(name="Stuck", url="https://stuck.example.com", status=STATUS_CHECKING))
    db.commit()

    assert len(recover_stale_checks(db)) == 1
    # A second startup must not re-fail an already-released target.
    assert recover_stale_checks(db) == []


async def test_released_target_can_be_checked_again(tmp_path: Path):
    """A recovered target must accept a new check, which is the whole point."""
    work_dir = make_work_dir("checks-recovered", tmp_path)
    db = make_session()
    target = Target(name="Stuck", url="https://example.com", status=STATUS_CHECKING)
    db.add(target)
    db.commit()
    db.refresh(target)

    recover_stale_checks(db)
    db.refresh(target)

    async def fake_capture(url: str, settings: Settings, out_dir: Path) -> CaptureResult:
        return write_capture(out_dir, "after-recovery", "Hello", "white")

    result = await run_target_check(
        db,
        target,
        Settings(DATA_DIR=str(work_dir)),
        capture_func=fake_capture,
    )

    assert result.status == STATUS_OK
    db.refresh(target)
    assert target.status == STATUS_OK
    assert target.last_error is None


# --- Multi-baseline matching (capture-improvements B4) ---


def _add_baseline(db: Session, target_id: str, capture: CaptureResult, minutes_old: int) -> None:
    db.add(
        Snapshot(
            id=capture.id,
            target_id=target_id,
            captured_at=datetime.now(UTC) - timedelta(minutes=minutes_old),
            final_url=capture.final_url,
            http_status=capture.http_status,
            title=capture.title,
            screenshot_path=capture.screenshot_path,
            text_path=capture.text_path,
            html_path=capture.html_path,
            is_baseline=True,
        )
    )
    db.commit()


async def test_run_target_check_matches_the_closest_of_several_baselines(tmp_path: Path):
    """A rotating page serving a previously approved variant must stay OK."""
    work_dir = make_work_dir("checks-multibaseline", tmp_path)
    db = make_session()
    target = Target(name="Example", url="https://example.com")
    db.add(target)
    db.commit()
    db.refresh(target)

    # Two approved appearances. The newest baseline is variant A.
    _add_baseline(db, target.id, write_capture(work_dir, "variant-b", "Variant B", "black"), 20)
    _add_baseline(db, target.id, write_capture(work_dir, "variant-a", "Variant A", "white"), 10)

    # The page now serves variant B, which is not the newest baseline.
    current = write_capture(work_dir, "current-b", "Variant B", "black")

    async def fake_capture(url: str, settings: Settings, out_dir: Path) -> CaptureResult:
        return current

    result = await run_target_check(
        db,
        target,
        Settings(DATA_DIR=str(work_dir)),
        capture_func=fake_capture,
    )

    assert result.check_result is not None
    # Compared against only the newest baseline this would have been Changed.
    assert result.status == STATUS_OK
    assert result.check_result.baseline_snapshot_id == "variant-b"
    assert result.check_result.visual_change_score == 0.0
    assert result.check_result.text_change_score == 0.0


async def test_run_target_check_reports_changed_when_no_baseline_matches(tmp_path: Path):
    work_dir = make_work_dir("checks-multibaseline-changed", tmp_path)
    db = make_session()
    target = Target(name="Example", url="https://example.com")
    db.add(target)
    db.commit()
    db.refresh(target)

    _add_baseline(db, target.id, write_capture(work_dir, "base-a", "Variant A", "white"), 20)
    _add_baseline(db, target.id, write_capture(work_dir, "base-b", "Variant B", "white"), 10)

    defaced = write_capture(work_dir, "defaced", "Hacked by attacker", "black")

    async def fake_capture(url: str, settings: Settings, out_dir: Path) -> CaptureResult:
        return defaced

    result = await run_target_check(
        db,
        target,
        Settings(DATA_DIR=str(work_dir)),
        capture_func=fake_capture,
    )

    assert result.status == STATUS_CHANGED
    assert result.check_result is not None
    assert result.check_result.visual_change_score > 0.0


async def test_run_target_check_respects_the_baseline_cap(tmp_path: Path):
    """Only the newest MAX_BASELINES_PER_TARGET baselines are consulted."""
    work_dir = make_work_dir("checks-baseline-cap", tmp_path)
    db = make_session()
    target = Target(name="Example", url="https://example.com")
    db.add(target)
    db.commit()
    db.refresh(target)

    # The matching variant is the oldest, and sits outside a cap of 2.
    _add_baseline(db, target.id, write_capture(work_dir, "old-match", "Old", "black"), 30)
    _add_baseline(db, target.id, write_capture(work_dir, "mid", "Mid", "white"), 20)
    _add_baseline(db, target.id, write_capture(work_dir, "new", "New", "white"), 10)

    current = write_capture(work_dir, "current-old", "Old", "black")

    async def fake_capture(url: str, settings: Settings, out_dir: Path) -> CaptureResult:
        return current

    result = await run_target_check(
        db,
        target,
        Settings(DATA_DIR=str(work_dir), MAX_BASELINES_PER_TARGET=2),
        capture_func=fake_capture,
    )

    assert result.status == STATUS_CHANGED
    assert result.check_result is not None
    assert result.check_result.baseline_snapshot_id in {"mid", "new"}


def test_diff_severity_matches_the_threshold_semantics():
    settings = Settings(TEXT_CHANGE_THRESHOLD=0.02, VISUAL_CHANGE_THRESHOLD=0.01)

    # severity > 1 must mean "either score exceeds its own threshold".
    assert diff_severity(_diff(0.0, 0.0), settings) == 0.0
    assert diff_severity(_diff(0.02, 0.01), settings) == 1.0  # at threshold, not over
    assert diff_severity(_diff(0.03, 0.0), settings) > 1.0  # text alone
    assert diff_severity(_diff(0.0, 0.02), settings) > 1.0  # visual alone


def test_diff_severity_treats_a_zero_threshold_as_zero_tolerance():
    settings = Settings(TEXT_CHANGE_THRESHOLD=0.0, VISUAL_CHANGE_THRESHOLD=0.0)

    assert diff_severity(_diff(0.0, 0.0), settings) == 0.0
    # Any change at all exceeds a zero threshold...
    assert diff_severity(_diff(0.000001, 0.0), settings) > 1.0
    # ...but severities stay finite and ordered, so baselines remain rankable.
    assert math.isfinite(diff_severity(_diff(0.5, 0.0), settings))
    assert diff_severity(_diff(0.5, 0.0), settings) > diff_severity(_diff(0.1, 0.0), settings)


def test_diff_severity_reports_a_structural_change_with_zero_tolerance_default():
    settings = Settings()
    assert settings.STRUCTURE_CHANGE_THRESHOLD == 0.0

    clean = DiffResult(text_change_score=0.0, visual_change_score=0.0, summary="")
    injected = DiffResult(
        text_change_score=0.0,
        visual_change_score=0.0,
        summary="",
        structure_change_score=0.01,
    )

    # A page identical in text and pixels but carrying a new script must still
    # be reported: that is the invisible-injection case.
    assert diff_severity(clean, settings) == 0.0
    assert diff_severity(injected, settings) > 1.0


def test_select_best_baseline_prefers_a_matching_baseline():
    settings = Settings(TEXT_CHANGE_THRESHOLD=0.02, VISUAL_CHANGE_THRESHOLD=0.01)
    comparisons = [
        ("far", _diff(0.5, 0.5)),
        ("match", _diff(0.001, 0.001)),
        ("near", _diff(0.03, 0.02)),
    ]

    chosen_id, chosen_diff = select_best_baseline(comparisons, settings)

    assert chosen_id == "match"
    assert diff_severity(chosen_diff, settings) <= 1.0


def test_select_best_baseline_returns_the_closest_when_none_match():
    settings = Settings(TEXT_CHANGE_THRESHOLD=0.02, VISUAL_CHANGE_THRESHOLD=0.01)
    comparisons = [("far", _diff(0.9, 0.9)), ("closest", _diff(0.05, 0.03))]

    chosen_id, _ = select_best_baseline(comparisons, settings)

    assert chosen_id == "closest"


def _diff(text_score: float, visual_score: float) -> DiffResult:
    return DiffResult(
        text_change_score=text_score,
        visual_change_score=visual_score,
        summary="test",
    )


# --- Structural detector end to end ---


def _write_capture_with_html(
    out_dir: Path,
    snapshot_id: str,
    text: str,
    color: str,
    body_html: str,
) -> CaptureResult:
    """Like write_capture, but with control over the stored HTML artifact."""
    capture = write_capture(out_dir, snapshot_id, text, color)
    Path(capture.html_path).write_text(
        f"<html><body>{body_html}</body></html>", encoding="utf-8"
    )
    return capture


async def test_run_target_check_flags_an_invisible_script_injection(tmp_path: Path):
    """Identical text and pixels, but a new external script: must be Changed.

    This is the case the text and visual detectors both miss, and the reason the
    structural detector exists.
    """
    work_dir = make_work_dir("checks-structure", tmp_path)
    db = make_session()
    target = Target(name="Example", url="https://example.com")
    db.add(target)
    db.commit()
    db.refresh(target)

    captures = [
        _write_capture_with_html(
            work_dir, "clean", "Same text", "white", "<h1>Same text</h1>"
        ),
        _write_capture_with_html(
            work_dir,
            "injected",
            "Same text",
            "white",
            '<h1>Same text</h1><script src="https://evil.example.net/p.js"></script>',
        ),
    ]

    async def fake_capture(url: str, settings: Settings, out_dir: Path) -> CaptureResult:
        return captures.pop(0)

    settings = Settings(DATA_DIR=str(work_dir))
    await run_target_check(db, target, settings, capture_func=fake_capture)
    result = await run_target_check(db, target, settings, capture_func=fake_capture)

    assert result.check_result is not None
    assert result.check_result.text_change_score == 0.0
    assert result.check_result.visual_change_score == 0.0
    assert result.check_result.structure_change_score > 0.0
    assert result.status == STATUS_CHANGED
    assert "evil.example.net" in result.check_result.summary


async def test_run_target_check_ignores_allowlisted_third_party(tmp_path: Path):
    work_dir = make_work_dir("checks-structure-allowed", tmp_path)
    db = make_session()
    target = Target(
        name="Example",
        url="https://example.com",
        allowed_domains=["googletagmanager.com"],
    )
    db.add(target)
    db.commit()
    db.refresh(target)

    captures = [
        _write_capture_with_html(work_dir, "before", "Same text", "white", "<h1>Same text</h1>"),
        _write_capture_with_html(
            work_dir,
            "after",
            "Same text",
            "white",
            '<h1>Same text</h1>'
            '<script src="https://www.googletagmanager.com/gtag/js?id=G-1"></script>',
        ),
    ]

    async def fake_capture(url: str, settings: Settings, out_dir: Path) -> CaptureResult:
        return captures.pop(0)

    settings = Settings(DATA_DIR=str(work_dir))
    await run_target_check(db, target, settings, capture_func=fake_capture)
    result = await run_target_check(db, target, settings, capture_func=fake_capture)

    assert result.check_result is not None
    assert result.check_result.structure_change_score == 0.0
    assert result.status == STATUS_OK


def _write_staged_capture(out_dir: Path, snapshot_id: str, text: str, color: str) -> CaptureResult:
    staging_dir = out_dir / "staging" / snapshot_id
    staging_dir.mkdir(parents=True, exist_ok=True)
    screenshot_path = staging_dir / f"{snapshot_id}.png"
    text_path = staging_dir / f"{snapshot_id}.txt"
    html_path = staging_dir / f"{snapshot_id}.html"

    Image.new("RGB", (2, 2), color).save(screenshot_path)
    text_path.write_text(text, encoding="utf-8")
    html_path.write_text(f"<html><body>{text}</body></html>", encoding="utf-8")

    return CaptureResult(
        id=snapshot_id,
        url=text,
        final_url=text,
        http_status=200,
        title="Test",
        screenshot_path=str(screenshot_path),
        text_path=str(text_path),
        html_path=str(html_path),
        redirect_count=0,
        staging_dir=str(staging_dir),
    )


async def test_run_target_check_discards_unchanged_staging_artifacts(tmp_path: Path):
    """Stage 1.2: Unchanged checks discard temporary files, consuming 0 bytes."""
    work_dir = make_work_dir("checks-discard-unchanged", tmp_path)
    db = make_session()
    target = Target(name="Example", url="https://example.com")
    db.add(target)
    db.commit()
    db.refresh(target)

    captures = [
        _write_staged_capture(work_dir, "baseline", "Hello world", "white"),
        _write_staged_capture(work_dir, "current-identical", "Hello world", "white"),
    ]

    async def fake_capture(url: str, settings: Settings, out_dir: Path) -> CaptureResult:
        return captures.pop(0)

    settings = Settings(DATA_DIR=str(work_dir))
    # First check: Baseline
    base_res = await run_target_check(db, target, settings, capture_func=fake_capture)
    assert base_res.status == STATUS_OK
    assert (work_dir / "screenshots" / "baseline.png").is_file()
    assert not (work_dir / "staging" / "baseline").exists()

    # Second check: Identical to baseline
    unchanged_res = await run_target_check(db, target, settings, capture_func=fake_capture)
    assert unchanged_res.status == STATUS_OK
    assert unchanged_res.check_result is not None
    assert unchanged_res.check_result.status == STATUS_OK
    assert unchanged_res.check_result.current_snapshot_id == "baseline"

    # Staging artifacts for the unchanged check were completely discarded
    assert not (work_dir / "staging" / "current-identical").exists()
    assert not (work_dir / "screenshots" / "current-identical.png").exists()


async def test_run_target_check_promotes_changed_staging_artifacts(tmp_path: Path):
    """Stage 1.2: Changed checks promote staged artifacts to permanent storage."""
    work_dir = make_work_dir("checks-promote-changed", tmp_path)
    db = make_session()
    target = Target(name="Example", url="https://example.com")
    db.add(target)
    db.commit()
    db.refresh(target)

    captures = [
        _write_staged_capture(work_dir, "baseline", "Hello world", "white"),
        _write_staged_capture(work_dir, "changed-run", "Defaced world", "red"),
    ]

    async def fake_capture(url: str, settings: Settings, out_dir: Path) -> CaptureResult:
        return captures.pop(0)

    settings = Settings(DATA_DIR=str(work_dir))
    await run_target_check(db, target, settings, capture_func=fake_capture)
    changed_res = await run_target_check(db, target, settings, capture_func=fake_capture)

    assert changed_res.status == STATUS_CHANGED
    assert changed_res.snapshot is not None
    assert changed_res.snapshot.id == "changed-run"
    assert (work_dir / "screenshots" / "changed-run.png").is_file()
    assert (work_dir / "text" / "changed-run.txt").is_file()
    assert not (work_dir / "staging" / "changed-run").exists()


async def test_run_target_check_discards_staging_on_diff_failure(tmp_path: Path):
    """Finding F5: A failure during diff processing discards staging files."""
    work_dir = make_work_dir("checks-cleanup-on-error", tmp_path)
    db = make_session()
    target = Target(name="Example", url="https://example.com")
    db.add(target)
    db.commit()
    db.refresh(target)

    # Initial baseline
    initial = _write_staged_capture(work_dir, "baseline", "Hello", "white")
    settings = Settings(DATA_DIR=str(work_dir))

    async def fake_initial(u: str, s: Settings, o: Path) -> CaptureResult:
        return initial

    await run_target_check(db, target, settings, capture_func=fake_initial)

    # Second check has invalid image that causes diff comparison error
    broken_capture = _write_staged_capture(work_dir, "broken", "Hello", "white")
    Path(broken_capture.screenshot_path).write_text("not an image")

    async def fake_broken(u: str, s: Settings, o: Path) -> CaptureResult:
        return broken_capture

    failed_res = await run_target_check(db, target, settings, capture_func=fake_broken)
    assert failed_res.status == STATUS_FAILED
    # Staging directory is cleaned up despite exception
    assert not (work_dir / "staging" / "broken").exists()


async def test_run_target_check_reports_availability_issue_on_timeout(tmp_path: Path):
    """Stage 1.3: Timeouts are classified as Availability Issue."""
    work_dir = make_work_dir("checks-avail-timeout", tmp_path)
    db = make_session()
    target = Target(name="Example", url="https://example.com")
    db.add(target)
    db.commit()
    db.refresh(target)

    async def timeout_capture(url: str, settings: Settings, out_dir: Path) -> CaptureResult:
        raise TimeoutError("Timeout 25000ms exceeded")

    settings = Settings(DATA_DIR=str(work_dir))
    res = await run_target_check(db, target, settings, capture_func=timeout_capture)
    assert res.status == STATUS_AVAILABILITY_ISSUE
    assert target.status == STATUS_AVAILABILITY_ISSUE


async def test_run_target_check_reports_availability_issue_on_5xx(tmp_path: Path):
    """Stage 1.3: HTTP 5xx responses are classified as Availability Issue."""
    work_dir = make_work_dir("checks-avail-5xx", tmp_path)
    db = make_session()
    target = Target(name="Example", url="https://example.com")
    db.add(target)
    db.commit()
    db.refresh(target)

    capture = _write_staged_capture(work_dir, "server-error", "503 Service Unavailable", "white")
    capture.http_status = 503

    async def fake_5xx(u: str, s: Settings, o: Path) -> CaptureResult:
        return capture

    settings = Settings(DATA_DIR=str(work_dir))
    res = await run_target_check(db, target, settings, capture_func=fake_5xx)
    assert res.status == STATUS_AVAILABILITY_ISSUE
    assert target.status == STATUS_AVAILABILITY_ISSUE
    assert "503" in (target.last_error or "")
    # Staged artifacts discarded
    assert not (work_dir / "staging" / "server-error").exists()


def test_reconcile_artifacts_purges_expired_staging_and_orphans(tmp_path: Path):
    """Finding F5: reconcile_artifacts cleans expired staging dirs and unreferenced files."""
    work_dir = make_work_dir("checks-reconcile", tmp_path)
    db = make_session()

    # Create a registered snapshot
    target = Target(name="Example", url="https://example.com")
    db.add(target)
    db.commit()
    db.refresh(target)
    snap = Snapshot(
        id="valid-snapshot",
        target_id=target.id,
        final_url="https://example.com",
        screenshot_path=str(work_dir / "screenshots" / "valid-snapshot.png"),
        text_path=str(work_dir / "text" / "valid-snapshot.txt"),
        html_path=str(work_dir / "html" / "valid-snapshot.html"),
        is_baseline=True,
    )
    db.add(snap)
    db.commit()

    # Valid file in screenshots
    valid_file = work_dir / "screenshots" / "valid-snapshot.png"
    valid_file.parent.mkdir(parents=True, exist_ok=True)
    valid_file.write_text("valid")

    # Orphan file in screenshots
    orphan_file = work_dir / "screenshots" / "orphan-snapshot.png"
    orphan_file.write_text("orphan")

    # Expired staging dir
    expired_staging = work_dir / "staging" / "old-abandoned"
    expired_staging.mkdir(parents=True, exist_ok=True)
    (expired_staging / "old.png").write_text("old")
    import os
    # Set mtime to 2 hours ago
    old_time = time.time() - 7200
    os.utime(expired_staging, (old_time, old_time))

    settings = Settings(DATA_DIR=str(work_dir), STAGING_CLEANUP_MAX_AGE_SECONDS=1800)
    stats = reconcile_artifacts(db, settings)

    assert stats["cleaned_staging"] == 1
    assert stats["cleaned_orphans"] == 1
    assert valid_file.is_file()
    assert not orphan_file.exists()
    assert not expired_staging.exists()

