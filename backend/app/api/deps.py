import hashlib
import secrets
from collections.abc import Generator
from datetime import timedelta
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session as DBSession

from app.core.config import Settings, get_settings
from app.core.time import utcnow
from app.db.session import SessionLocal
from app.models.session import Session
from app.models.user import User
from app.services.capture.capture import capture_snapshot
from app.services.checks import CaptureFunc
from app.services.concurrency import SessionFactory

UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def get_capture_func() -> CaptureFunc:
    return capture_snapshot


def get_session_factory() -> SessionFactory:
    return SessionLocal


def get_db() -> Generator[DBSession, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _validate_csrf(request: Request, session: Session, settings: Settings) -> None:
    """Enforce the synchronizer CSRF token on state-changing requests.

    Safe methods (GET/HEAD/OPTIONS) are exempt. For mutations the caller must
    echo the session's CSRF token in the configured header; a constant-time
    comparison avoids leaking validity through timing.
    """
    if request.method not in UNSAFE_METHODS:
        return
    header_token = request.headers.get(settings.CSRF_HEADER_NAME)
    if not header_token or not secrets.compare_digest(header_token, session.csrf_token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF verification failed",
        )


def get_current_session(
    request: Request,
    db: Annotated[DBSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Session:
    session_id = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if not session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    token_hash = hash_token(session_id)
    session = db.query(Session).filter(Session.token_hash == token_hash).first()
    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session",
        )

    now = utcnow()
    if session.revoked_at is not None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session revoked")
    if now > session.absolute_expires_at:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")
    if now > session.idle_expires_at:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session idle timeout")

    _validate_csrf(request, session, settings)

    # Refresh activity in a bounded manner so we do not write on every request.
    if (now - session.last_seen_at).total_seconds() > settings.SESSION_ACTIVITY_REFRESH_SECONDS:
        session.last_seen_at = now
        session.idle_expires_at = now + timedelta(seconds=settings.SESSION_IDLE_TIMEOUT_SECONDS)
        db.commit()

    return session


def get_current_user(
    db: Annotated[DBSession, Depends(get_db)],
    session: Annotated[Session, Depends(get_current_session)],
) -> User:
    user = db.query(User).filter(User.id == session.user_id).first()
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )
    return user


__all__ = [
    "Settings",
    "get_capture_func",
    "get_current_session",
    "get_current_user",
    "get_db",
    "get_session_factory",
    "get_settings",
    "hash_token",
]
