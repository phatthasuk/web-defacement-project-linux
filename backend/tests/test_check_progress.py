from datetime import timedelta

from app.core.time import utcnow
from app.services import check_progress


def test_progress_is_scoped_to_run_and_url_revision() -> None:
    record = check_progress.register_queued("target-a", "run-a", 1)

    assert check_progress.get_progress("target-a", "run-a", 1) is not None
    assert check_progress.get_progress("target-a", "run-b", 1) is None
    assert check_progress.get_progress("target-a", "run-a", 2) is None

    check_progress._records.pop(record.target_id, None)


def test_progress_serializes_real_steps_and_finished_ttl() -> None:
    record = check_progress.register_queued("target-b", "run-b", 3)
    token = check_progress.bind_progress(record)
    try:
        check_progress.begin_attempt(record, 1)
        check_progress.set_phase("opening_page")
        check_progress.set_phase("capturing")
        check_progress.finish_progress("OK")
    finally:
        check_progress.reset_progress(token)

    result = check_progress.get_progress("target-b", None, 3)
    assert result is not None
    assert result["state"] == "finished"
    steps = result["steps"]
    assert isinstance(steps, list)
    assert [step["state"] for step in steps] == ["completed", "completed", "completed"]

    record.finished_at = utcnow() - timedelta(seconds=check_progress.FINISHED_TTL_SECONDS + 1)
    assert check_progress.get_progress("target-b", None, 3) is None


def test_stale_run_cannot_replace_newer_progress() -> None:
    old = check_progress.register_queued("target-c", "old-run", 1)
    token = check_progress.bind_progress(old)
    try:
        newer = check_progress.register_queued("target-c", "new-run", 1)
        check_progress.finish_progress("Failed", "check_interrupted")
    finally:
        check_progress.reset_progress(token)

    assert check_progress.get_progress_record("target-c", "new-run", 1) is newer
    check_progress._records.pop("target-c", None)


def test_skipped_phase_closes_previous_operation_and_terminal_has_no_running_steps() -> None:
    record = check_progress.register_queued("target-skip", "run-skip", 1)
    token = check_progress.bind_progress(record)
    try:
        check_progress.begin_attempt(record, 1)
        check_progress.set_phase("opening_page")
        check_progress.set_phase("capturing")
        check_progress.skip_phase("comparing")
        check_progress.set_phase("saving_result")
        check_progress.finish_progress("Awaiting Baseline")
    finally:
        check_progress.reset_progress(token)

    assert [(step.phase, step.state) for step in record.steps] == [
        ("queued", "completed"),
        ("opening_page", "completed"),
        ("capturing", "completed"),
        ("comparing", "skipped"),
        ("saving_result", "completed"),
    ]
    assert all(step.finished_at is not None for step in record.steps)
    assert not any(step.state == "running" for step in record.steps)
    check_progress._records.pop("target-skip", None)


def test_skipping_readiness_closes_navigation_before_capture() -> None:
    record = check_progress.register_queued("target-ready", "run-ready", 1)
    token = check_progress.bind_progress(record)
    try:
        check_progress.begin_attempt(record, 1)
        check_progress.set_phase("opening_page")
        check_progress.skip_phase("waiting_page_ready")
        check_progress.set_phase("capturing")
    finally:
        check_progress.reset_progress(token)

    assert [(step.phase, step.state) for step in record.steps[-3:]] == [
        ("opening_page", "completed"),
        ("waiting_page_ready", "skipped"),
        ("capturing", "running"),
    ]
    check_progress._records.pop("target-ready", None)
