from datetime import UTC, datetime
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

MemberState = Literal["pending", "active", "suspended", "rejected"]
MemberRole = Literal["admin", "operator"]
RegistrationStatus = Literal["pending", "approved", "rejected"]


class MemberCreate(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    display_name: str = Field(min_length=1, max_length=100)
    temporary_password: str = Field(min_length=12, max_length=200)
    model_config = ConfigDict(extra="forbid")

    @field_validator("username", "display_name")
    @classmethod
    def trim_fields(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Must not be empty")
        return value


class MemberUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    is_active: bool | None = None
    model_config = ConfigDict(extra="forbid")

    @field_validator("display_name")
    @classmethod
    def trim_display_name(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("Display name must not be empty")
        return value.strip() if value is not None else None

    @model_validator(mode="after")
    def require_nonempty_patch(self) -> "MemberUpdate":
        if not self.model_fields_set:
            raise ValueError("At least one member field must be provided")
        if "display_name" in self.model_fields_set and self.display_name is None:
            raise ValueError("Display name must not be null")
        if "is_active" in self.model_fields_set and self.is_active is None:
            raise ValueError("Account status must not be null")
        return self


class RejectMember(BaseModel):
    reason: str | None = Field(default=None, max_length=1000)
    model_config = ConfigDict(extra="forbid")


class ResetPassword(BaseModel):
    temporary_password: str = Field(min_length=12, max_length=200)
    model_config = ConfigDict(extra="forbid")


class MemberRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    display_name: str
    role: MemberRole
    is_active: bool
    status: MemberState
    registration_status: RegistrationStatus
    registration_at: datetime
    registration_reviewed_at: datetime | None = None
    registration_reviewed_by: int | None = None
    registration_rejection_reason: str | None = None
    last_login_at: datetime | None = None
    must_change_password: bool
    assigned_website_count: int
    created_at: datetime

    @field_serializer(
        "registration_at",
        "registration_reviewed_at",
        "last_login_at",
        "created_at",
    )
    def serialize_datetime(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.isoformat().replace("+00:00", "Z")


class PaginatedMembersRead(BaseModel):
    items: list[MemberRead]
    total: int
    pending_count: int
    limit: int
    offset: int


class TargetAssigneeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    display_name: str
    is_active: bool


class MemberWebsiteTagRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    color_key: str


class MemberWebsiteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    url: str
    is_active: bool
    tags: list[MemberWebsiteTagRead] = Field(default_factory=list)
    assignees: list[TargetAssigneeRead] = Field(default_factory=list)


class MemberWebsitesCountsRead(BaseModel):
    all: int
    unassigned: int
    assigned: int


class PaginatedMemberWebsitesRead(BaseModel):
    items: list[MemberWebsiteRead]
    total: int
    counts: MemberWebsitesCountsRead
    limit: int
    offset: int


class MemberWebsitesListRead(BaseModel):
    items: list[MemberWebsiteRead]
    total: int
    limit: int
    offset: int
