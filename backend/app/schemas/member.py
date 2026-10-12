from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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
