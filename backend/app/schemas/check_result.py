from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, field_serializer


class CheckResultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    target_id: str
    baseline_snapshot_id: str
    current_snapshot_id: str
    created_at: datetime
    status: str
    text_change_score: float
    visual_change_score: float
    structure_change_score: float = 0.0
    summary: str
    acknowledged_at: datetime | None

    @field_serializer("created_at")
    def _serialize_created_at(self, dt: datetime) -> str:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.isoformat().replace("+00:00", "Z")

    @field_serializer("acknowledged_at")
    def _serialize_acknowledged_at(self, dt: datetime | None) -> str | None:
        if dt is None:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.isoformat().replace("+00:00", "Z")
