from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, field_serializer


class AuditEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    actor_id: int | None
    action: str
    member_id: int | None
    target_id: str | None
    source: str
    occurred_at: datetime
    before: dict | None
    after: dict | None
    details: str | None

    @field_serializer("occurred_at")
    def serialize_datetime(self, value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.isoformat().replace("+00:00", "Z")
