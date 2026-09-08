from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, field_serializer


class SnapshotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    target_id: str
    captured_at: datetime
    final_url: str
    http_status: int | None
    title: str | None
    is_baseline: bool

    @field_serializer("captured_at")
    def _serialize_captured_at(self, dt: datetime) -> str:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.isoformat().replace("+00:00", "Z")
