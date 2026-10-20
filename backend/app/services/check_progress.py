"""Bounded, process-local progress for the single-worker check pipeline."""

from __future__ import annotations

from collections import OrderedDict
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.core.time import utcnow

MAX_PROGRESS_TARGETS = 500
FINISHED_TTL_SECONDS = 60
PHASES = (
    "queued",
    "opening_page",
    "waiting_page_ready",
    "capturing",
    "comparing",
    "saving_result",
)


@dataclass
class ProgressStep:
    phase: str
    state: str
    started_at: datetime
    finished_at: datetime | None = None


@dataclass
class ProgressRecord:
    target_id: str
    run_id: str
    url_revision: int
    attempt_number: int
    attempt_started_at: datetime
    phase: str
    phase_started_at: datetime
    updated_at: datetime
    state: str = "queued"
    finished_at: datetime | None = None
    outcome: str | None = None
    error_code: str | None = None
    steps: list[ProgressStep] = field(default_factory=list)

    def serialize(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "url_revision": self.url_revision,
            "attempt_number": self.attempt_number,
            "phase": self.phase,
            "state": self.state,
            "attempt_started_at": _iso(self.attempt_started_at),
            "phase_started_at": _iso(self.phase_started_at),
            "updated_at": _iso(self.updated_at),
            "finished_at": _iso(self.finished_at),
            "outcome": self.outcome,
            "error_code": self.error_code,
            "steps": [
                {
                    "phase": step.phase,
                    "state": step.state,
                    "started_at": _iso(step.started_at),
                    "finished_at": _iso(step.finished_at),
                }
                for step in self.steps
            ],
        }


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() + "Z" if value is not None else None


_records: OrderedDict[str, ProgressRecord] = OrderedDict()
_current: ContextVar[ProgressRecord | None] = ContextVar("check_progress", default=None)


def current_progress() -> ProgressRecord | None:
    return _current.get()


def bind_progress(record: ProgressRecord):
    return _current.set(record)


def reset_progress(token: object) -> None:
    _current.reset(token)  # type: ignore[arg-type]


def register_queued(
    target_id: str, run_id: str, url_revision: int, attempt_number: int = 0
) -> ProgressRecord:
    now = utcnow()
    previous = _records.get(target_id)
    if previous is not None and previous.run_id == run_id:
        return previous
    record = ProgressRecord(
        target_id=target_id,
        run_id=run_id,
        url_revision=url_revision,
        attempt_number=attempt_number,
        attempt_started_at=now,
        phase="queued",
        phase_started_at=now,
        updated_at=now,
        steps=[ProgressStep("queued", "running", now)],
    )
    _records[target_id] = record
    _records.move_to_end(target_id)
    _evict()
    return record


def begin_attempt(record: ProgressRecord, attempt_number: int) -> None:
    now = utcnow()
    record.attempt_number = attempt_number
    record.attempt_started_at = now
    record.steps = []
    record.state = "queued"
    record.phase = "queued"
    record.phase_started_at = now
    record.updated_at = now
    record.steps.append(ProgressStep("queued", "running", now))


def set_phase(phase: str) -> None:
    record = current_progress()
    if record is None or phase not in PHASES:
        return
    if record.phase == phase and record.state == "running":
        return
    now = utcnow()
    _close_active_step(record, "completed", now)
    record.phase = phase
    record.phase_started_at = now
    record.updated_at = now
    record.state = "running"
    record.steps.append(ProgressStep(phase, "running", now))


def skip_phase(phase: str) -> None:
    record = current_progress()
    if record is None:
        return
    now = utcnow()
    _close_active_step(record, "completed", now)
    record.steps.append(ProgressStep(phase, "skipped", now, now))
    record.updated_at = now


def finish_progress(outcome: str, error_code: str | None = None) -> None:
    record = current_progress()
    if record is None:
        return
    now = utcnow()
    _close_active_step(record, "failed" if error_code else "completed", now)
    record.state = "finished"
    record.outcome = outcome
    record.error_code = error_code
    record.finished_at = now
    record.updated_at = now
    if _records.get(record.target_id) is record:
        _records.move_to_end(record.target_id)
        _evict()


def retry_wait(record: ProgressRecord, error_code: str | None) -> None:
    now = utcnow()
    _close_active_step(record, "failed", now)
    record.phase = "queued"
    record.phase_started_at = now
    record.updated_at = now
    record.state = "retry_wait"
    record.error_code = error_code
    record.steps.append(ProgressStep("queued", "retry_wait", now))


def _close_active_step(record: ProgressRecord, state: str, now: datetime) -> None:
    for step in reversed(record.steps):
        if step.state == "running":
            step.state = state
            step.finished_at = now
            return


def get_progress(target_id: str, run_id: str | None, url_revision: int) -> dict[str, object] | None:
    record = get_progress_record(target_id, run_id, url_revision)
    return record.serialize() if record is not None else None


def get_progress_record(
    target_id: str, run_id: str | None, url_revision: int
) -> ProgressRecord | None:
    _evict()
    record = _records.get(target_id)
    if record is None or record.url_revision != url_revision:
        return None
    if run_id is None and record.state == "finished":
        return record
    if record.run_id != run_id:
        return None
    return record


def _evict() -> None:
    now = utcnow()
    for target_id, record in list(_records.items()):
        if record.finished_at and (now - record.finished_at) > timedelta(
            seconds=FINISHED_TTL_SECONDS
        ):
            _records.pop(target_id, None)
    while len(_records) > MAX_PROGRESS_TARGETS:
        _records.popitem(last=False)
