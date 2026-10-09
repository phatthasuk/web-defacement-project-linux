import unicodedata
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

TAG_COLORS = frozenset({"cyan", "blue", "violet", "emerald", "amber", "rose", "slate"})
TagColor = Literal["cyan", "blue", "violet", "emerald", "amber", "rose", "slate"]


def normalize_tag_name(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip().casefold()


class TagCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=50)
    color_key: TagColor = "cyan"
    parent_id: str | None = None

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        name = unicodedata.normalize("NFKC", value).strip()
        if not name:
            raise ValueError("Name must not be blank")
        return name


class TagUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=50)
    color_key: TagColor | None = None
    parent_id: str | None = None

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        name = unicodedata.normalize("NFKC", value).strip()
        if not name:
            raise ValueError("Name must not be blank")
        return name


class TagRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    color_key: TagColor
    parent_id: str | None = None
    parent_name: str | None = None
    target_count: int = 0
    created_at: datetime
    updated_at: datetime

    @field_serializer("created_at", "updated_at")
    def serialize_datetime(self, value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.isoformat().replace("+00:00", "Z")


class PaginatedTagsRead(BaseModel):
    items: list[TagRead]
    total: int
    limit: int
    offset: int
