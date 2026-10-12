from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class UserRead(BaseModel):
    id: int
    username: str
    is_active: bool
    role: Literal["admin", "operator"]
    display_name: str
    registration_status: str
    must_change_password: bool

    model_config = ConfigDict(from_attributes=True)


class AuthResponse(UserRead):
    """User identity plus the CSRF token for the current session.

    The frontend and backend run on different origins, so the CSRF token cannot
    be read from a cookie by the browser. It is returned in the response body,
    held in memory, and echoed back in the CSRF header on every mutation.
    """

    csrf_token: str


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=1, max_length=200)

    model_config = ConfigDict(extra="forbid")


class RegistrationRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)
    display_name: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=12, max_length=200)
    password_confirmation: str = Field(..., min_length=12, max_length=200)

    model_config = ConfigDict(extra="forbid")

    @field_validator("username", "display_name")
    @classmethod
    def trim_required(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Must not be empty")
        return value

    @field_validator("password_confirmation")
    @classmethod
    def confirmation_matches(cls, value: str, info) -> str:
        password = info.data.get("password")
        if password is not None and value != password:
            raise ValueError("Passwords do not match")
        return value


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=200)
    new_password: str = Field(..., min_length=12, max_length=200)

    model_config = ConfigDict(extra="forbid")
