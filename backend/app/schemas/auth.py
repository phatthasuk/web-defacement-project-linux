from pydantic import BaseModel, ConfigDict, Field


class UserRead(BaseModel):
    id: int
    username: str
    is_active: bool
    role: str

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
