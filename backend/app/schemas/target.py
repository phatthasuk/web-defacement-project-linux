from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, field_serializer

ALLOWED_DOMAINS_DESCRIPTION = (
    "Hosts whose scripts, iframes, forms and outbound links are expected on this "
    "target (analytics, tag managers, CDNs). Subdomains of a listed host are "
    "covered. Anything not listed is reported by the structural detector."
)


class TargetCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    url: str = Field(min_length=1, max_length=2048)
    allowed_domains: list[str] | None = Field(
        default=None, max_length=200, description=ALLOWED_DOMAINS_DESCRIPTION
    )


class TargetUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    url: str | None = Field(default=None, min_length=1, max_length=2048)
    is_active: bool | None = None
    allowed_domains: list[str] | None = Field(
        default=None, max_length=200, description=ALLOWED_DOMAINS_DESCRIPTION
    )


class TargetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    url: str
    status: str
    is_active: bool
    last_error: str | None = None
    allowed_domains: list[str] | None = None
    created_at: datetime
    updated_at: datetime

    @field_serializer("created_at", "updated_at")
    def _serialize_datetime(self, dt: datetime) -> str:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.isoformat().replace("+00:00", "Z")


class PaginatedTargetsRead(BaseModel):
    items: list[TargetRead]
    total: int
    limit: int
    offset: int

