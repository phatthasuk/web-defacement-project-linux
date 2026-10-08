from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

from app.schemas.tag import TagRead

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
    tag_ids: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("tag_ids")
    @classmethod
    def unique_tag_ids(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("Tag IDs must be unique")
        return value


class TargetUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    url: str | None = Field(default=None, min_length=1, max_length=2048)
    is_active: bool | None = None
    allowed_domains: list[str] | None = Field(
        default=None, max_length=200, description=ALLOWED_DOMAINS_DESCRIPTION
    )
    tag_ids: list[str] | None = Field(default=None, max_length=20)

    @field_validator("name", "url", "is_active", "tag_ids", mode="before")
    @classmethod
    def reject_explicit_null(cls, value: object) -> object:
        # Defaults are not validated: omitted fields still support partial PATCH.
        if value is None:
            raise ValueError("Field must not be null")
        return value

    @field_validator("tag_ids")
    @classmethod
    def unique_tag_ids(cls, value: list[str] | None) -> list[str] | None:
        if value is not None and len(value) != len(set(value)):
            raise ValueError("Tag IDs must be unique")
        return value


class TargetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    url: str
    url_revision: int
    status: str
    is_active: bool
    last_error: str | None = None
    latest_structure_change_score: float | None = None
    allowed_domains: list[str] | None = None
    tags: list[TagRead] = Field(default_factory=list)
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

