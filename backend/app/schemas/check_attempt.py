from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, field_serializer


class CheckAttemptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    target_id: str
    url_revision: int
    run_id: str
    attempt_number: int
    source: str
    actor_id: int | None
    started_at: datetime
    finished_at: datetime | None
    status: str
    error_code: str | None
    error_message: str | None
    http_status: int | None
    check_result_id: str | None
    snapshot_id: str | None

    @field_serializer("started_at", "finished_at")
    def serialize_datetime(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.isoformat().replace("+00:00", "Z")
