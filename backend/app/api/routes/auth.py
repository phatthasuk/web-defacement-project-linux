import logging
import secrets
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session as DbSession

from app.api.deps import get_current_session, get_current_user, get_db, hash_token
from app.core.config import Settings, get_settings
from app.core.security import get_password_hash, verify_password
from app.core.time import utcnow
from app.models.session import Session
from app.models.user import User
from app.schemas.auth import AuthResponse, LoginRequest

logger = logging.getLogger("app.auth")

router = APIRouter(tags=["auth"])
limiter = Limiter(key_func=get_remote_address)

DatabaseSession = Annotated[DbSession, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]

settings = get_settings()

# Precomputed once so the "unknown user" and "locked account" paths spend roughly
# the same time in Argon2 as a real password check, reducing timing side channels.
_DUMMY_HASH = get_password_hash("dummy-password-for-constant-time-login")

GENERIC_LOGIN_ERROR = "Invalid username or password"


def _set_session_cookie(response: Response, raw_token: str, settings: Settings) -> None:
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=raw_token,
        httponly=True,
        secure=settings.SESSION_COOKIE_SECURE,
        samesite=settings.SESSION_COOKIE_SAMESITE,
        path=settings.SESSION_COOKIE_PATH,
        max_age=settings.SESSION_ABSOLUTE_LIFETIME_SECONDS,
    )


def _delete_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=settings.SESSION_COOKIE_NAME,
        httponly=True,
        secure=settings.SESSION_COOKIE_SECURE,
        samesite=settings.SESSION_COOKIE_SAMESITE,
        path=settings.SESSION_COOKIE_PATH,
    )


def _record_failed_attempt(user: User, settings: Settings) -> None:
    now = utcnow()
    window = settings.LOGIN_FAILURE_WINDOW_SECONDS
    first_failure = user.first_failed_login_at
    if first_failure is None or (now - first_failure).total_seconds() > window:
        user.first_failed_login_at = now
        user.failed_login_count = 1
    else:
        user.failed_login_count += 1

    if user.failed_login_count >= settings.LOGIN_MAX_FAILED_ATTEMPTS:
        user.locked_until = now + timedelta(seconds=settings.LOGIN_LOCKOUT_SECONDS)


def _reset_failed_attempts(user: User) -> None:
    user.failed_login_count = 0
    user.first_failed_login_at = None
    user.locked_until = None


@router.post("/login", response_model=AuthResponse)
@limiter.limit(settings.LOGIN_RATE_LIMIT)
async def login(
    request: Request,
    payload: LoginRequest,
    response: Response,
    db: DatabaseSession,
    settings: AppSettings,
) -> AuthResponse:
    username = payload.username.strip()
    user = db.query(User).filter(User.username == username).first()

    # Unknown user: keep timing comparable and return the generic error.
    if not user:
        verify_password(payload.password, _DUMMY_HASH)
        logger.info("login_failed reason=unknown_user username=%r", username)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=GENERIC_LOGIN_ERROR)

    now = utcnow()

    # Locked account: reject without revealing the state, keep timing comparable.
    if user.locked_until is not None and now < user.locked_until:
        verify_password(payload.password, _DUMMY_HASH)
        logger.warning("login_failed reason=locked user_id=%s", user.id)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=GENERIC_LOGIN_ERROR)

    password_ok = verify_password(payload.password, user.hashed_password)

    if not password_ok:
        _record_failed_attempt(user, settings)
        db.commit()
        logger.info(
            "login_failed reason=bad_password user_id=%s failed_count=%s",
            user.id,
            user.failed_login_count,
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=GENERIC_LOGIN_ERROR)

    # Correct password but disabled account: do not count as a brute-force attempt
    # and do not reveal that the account exists but is inactive.
    if not user.is_active:
        logger.warning("login_failed reason=inactive user_id=%s", user.id)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=GENERIC_LOGIN_ERROR)

    _reset_failed_attempts(user)

    # A fresh random token on every login rotates the session identifier and
    # prevents session fixation.
    raw_token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)

    session_record = Session(
        token_hash=hash_token(raw_token),
        user_id=user.id,
        csrf_token=csrf_token,
        created_at=now,
        last_seen_at=now,
        absolute_expires_at=now + timedelta(seconds=settings.SESSION_ABSOLUTE_LIFETIME_SECONDS),
        idle_expires_at=now + timedelta(seconds=settings.SESSION_IDLE_TIMEOUT_SECONDS),
    )
    db.add(session_record)
    db.commit()

    _set_session_cookie(response, raw_token, settings)
    logger.info("login_success user_id=%s", user.id)

    return AuthResponse(
        id=user.id,
        username=user.username,
        is_active=user.is_active,
        role=user.role,
        csrf_token=csrf_token,
    )


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    db: DatabaseSession,
    settings: AppSettings,
) -> dict:
    session_id = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if session_id:
        session_record = (
            db.query(Session).filter(Session.token_hash == hash_token(session_id)).first()
        )
        if session_record is not None and session_record.revoked_at is None:
            # Only a request carrying the matching CSRF token may revoke the session.
            header_token = request.headers.get(settings.CSRF_HEADER_NAME)
            if not header_token or not secrets.compare_digest(
                header_token, session_record.csrf_token
            ):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="CSRF verification failed",
                )
            session_record.revoked_at = utcnow()
            session_record.revocation_reason = "user_logout"
            db.commit()
            logger.info("logout user_id=%s", session_record.user_id)

    _delete_session_cookie(response, settings)
    return {"status": "ok"}


@router.get("/me", response_model=AuthResponse)
async def get_me(
    current_user: Annotated[User, Depends(get_current_user)],
    current_session: Annotated[Session, Depends(get_current_session)],
) -> AuthResponse:
    return AuthResponse(
        id=current_user.id,
        username=current_user.username,
        is_active=current_user.is_active,
        role=current_user.role,
        csrf_token=current_session.csrf_token,
    )
