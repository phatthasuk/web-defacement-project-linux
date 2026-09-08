import secrets
from collections.abc import AsyncIterator, Callable, Iterator
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import get_capture_func, get_db, get_session_factory, get_settings, hash_token
from app.api.routes.auth import limiter
from app.core.config import Settings
from app.core.security import get_password_hash
from app.core.time import utcnow
from app.db.session import Base
from app.main import app
from app.models.session import Session as AuthSession
from app.models.user import User
from app.services.capture.capture import CaptureResult


@pytest.fixture(autouse=True)
def disable_login_rate_limiter() -> Iterator[None]:
    """Keep the per-IP slowapi limiter out of functional tests.

    Its state is process-global and in-memory, which makes deterministic
    lockout/login assertions impossible. Per-IP throttling is delegated to
    slowapi; the custom lockout logic is what these tests exercise.
    """
    original = limiter.enabled
    limiter.enabled = False
    try:
        yield
    finally:
        limiter.enabled = original


@pytest.fixture
def api_work_dir(tmp_path: Path) -> Path:
    work_dir = tmp_path / f"api-{uuid4()}"
    work_dir.mkdir(parents=True, exist_ok=True)
    return work_dir


@pytest.fixture
def api_session_factory(api_work_dir: Path) -> Callable[[], Session]:
    engine = create_engine(
        f"sqlite:///{api_work_dir / 'api.db'}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def api_capture_calls() -> list[str]:
    return []


@pytest.fixture(autouse=True)
def api_dependency_overrides(
    api_work_dir: Path,
    api_session_factory: Callable[[], Session],
    api_capture_calls: list[str],
) -> Iterator[None]:
    settings = Settings(DATA_DIR=str(api_work_dir), PAGE_TIMEOUT_SECONDS=1)

    def override_get_db() -> Iterator[Session]:
        db = api_session_factory()
        try:
            yield db
        finally:
            db.close()

    async def default_capture(url: str, settings: Settings, out_dir: Path) -> CaptureResult:
        api_capture_calls.append(url)
        return write_capture(out_dir, f"capture-{uuid4()}", url, "white")

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_capture_func] = lambda: default_capture
    app.dependency_overrides[get_session_factory] = lambda: api_session_factory
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def auth_credentials(api_session_factory: Callable[[], Session]) -> dict[str, str]:
    """Seed a user and an active session, returning the raw cookie/CSRF tokens.

    This exercises the real authentication path (cookie -> hashed lookup ->
    session validation) rather than overriding get_current_user.
    """
    raw_token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)
    password = "correct horse battery staple"
    now = utcnow()
    with api_session_factory() as db:
        user = User(
            username="tester",
            hashed_password=get_password_hash(password),
            is_active=True,
            role="authenticated-user",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        db.add(
            AuthSession(
                token_hash=hash_token(raw_token),
                user_id=user.id,
                csrf_token=csrf_token,
                created_at=now,
                last_seen_at=now,
                absolute_expires_at=now + timedelta(days=14),
                idle_expires_at=now + timedelta(days=1),
            )
        )
        db.commit()
        user_id = user.id
    return {
        "session_token": raw_token,
        "csrf_token": csrf_token,
        "user_id": str(user_id),
        "username": "tester",
        "password": password,
    }


@pytest_asyncio.fixture
async def client(auth_credentials: dict[str, str]) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    cookies = httpx.Cookies()
    cookies.set("session_id", auth_credentials["session_token"])
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
        cookies=cookies,
        headers={"X-CSRF-Token": auth_credentials["csrf_token"]},
    ) as test_client:
        yield test_client


@pytest_asyncio.fixture
async def unauth_client() -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as test_client:
        yield test_client


def write_capture(out_dir: Path, snapshot_id: str, text: str, color: str) -> CaptureResult:
    screenshot_path = out_dir / "screenshots" / f"{snapshot_id}.png"
    text_path = out_dir / "text" / f"{snapshot_id}.txt"
    html_path = out_dir / "html" / f"{snapshot_id}.html"

    screenshot_path.parent.mkdir(parents=True, exist_ok=True)
    text_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.parent.mkdir(parents=True, exist_ok=True)

    Image.new("RGB", (2, 2), color).save(screenshot_path)
    text_path.write_text(text, encoding="utf-8")
    html_path.write_text(f"<html><body>{text}</body></html>", encoding="utf-8")

    return CaptureResult(
        id=snapshot_id,
        url=text,
        final_url=text,
        http_status=200,
        title="Example",
        screenshot_path=str(screenshot_path),
        text_path=str(text_path),
        html_path=str(html_path),
        redirect_count=0,
    )
