from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, field_serializer


class CheckProgressStepRead(BaseModel):
    phase: str
    state: Literal["running", "completed", "skipped", "failed", "retry_wait"]
    started_at: datetime
    finished_at: datetime | None

    @field_serializer("started_at", "finished_at")
    def serialize_datetime(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.isoformat().replace("+00:00", "Z")


class CheckProgressRead(BaseModel):
    run_id: str
    url_revision: int
    attempt_number: int
    phase: str
    state: Literal["queued", "running", "retry_wait", "finished"]
    attempt_started_at: datetime
    phase_started_at: datetime
    updated_at: datetime
    finished_at: datetime | None
    outcome: str | None
    error_code: str | None
    steps: list[CheckProgressStepRead]

    @field_serializer(
        "attempt_started_at", "phase_started_at", "updated_at", "finished_at"
    )
    def serialize_datetime(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.isoformat().replace("+00:00", "Z")


class ActiveCheckRead(BaseModel):
    id: str
    name: str
    status: str
    url_revision: int
    check_run_id: str
    check_run_source: str | None
    check_attempt_count: int
    check_retry_max_attempts: int
    next_check_at: datetime | None
    last_error_code: str | None
    progress: CheckProgressRead | None

    @field_serializer("next_check_at")
    def serialize_datetime(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.isoformat().replace("+00:00", "Z")


class CheckActivityRead(BaseModel):
    items: list[ActiveCheckRead]
    total: int
    limit: int
    offset: int
    observed_at: datetime

    @field_serializer("observed_at")
    def serialize_observed_at(self, value: datetime) -> str:
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
