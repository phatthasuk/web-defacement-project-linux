import os
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import select

from app.api.routes import (
    audit,
    auth,
    checks,
    config,
    members,
    review,
    snapshots,
    tags,
    targets,
)
from app.api.routes.auth import limiter
from app.core.config import get_settings
from app.core.errors import (
    ConflictError,
    DnsResolutionError,
    NotFoundError,
    SsrfBlockedError,
    ValidationError,
)
from app.core.status import InvalidStatusTransitionError
from app.db.session import SessionLocal
from app.models import (  # noqa: F401  (registers tables on Base)
    CheckResult,
    MemberAuditEvent,
    Session,
    Snapshot,
    Tag,
    Target,
    TargetTag,
    User,
    UserTargetAssignment,
)
from app.services.checks import reconcile_artifacts, recover_stale_checks
from app.services.scheduler import CheckScheduler

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.validate_retry_settings()
    # Fail closed if production and secure cookies are disabled
    if settings.ENVIRONMENT == "production" and not settings.SESSION_COOKIE_SECURE:
        raise RuntimeError("Production environment must run with SESSION_COOKIE_SECURE=True")

    # Create data directories if they don't exist BEFORE opening the SQLite database
    os.makedirs(settings.data_dir_path, exist_ok=True)
    os.makedirs(settings.data_dir_path / "screenshots", exist_ok=True)
    os.makedirs(settings.data_dir_path / "raw_screenshots", exist_ok=True)
    os.makedirs(settings.data_dir_path / "text", exist_ok=True)
    os.makedirs(settings.data_dir_path / "html", exist_ok=True)
    os.makedirs(settings.data_dir_path / "staging", exist_ok=True)

    if settings.DATABASE_URL.startswith("sqlite"):
        db_path_str = settings.DATABASE_URL.replace("sqlite:///", "").split("?")[0]
        if db_path_str and not db_path_str.startswith(":memory:"):
            db_dir = Path(db_path_str).parent
            if db_dir:
                os.makedirs(db_dir, exist_ok=True)

    # Production schema changes are applied by the deployment migration step.
    with SessionLocal() as db:
        bootstrap_admin = db.scalar(
            select(User.id)
            .where(
                User.role == "admin",
                User.registration_status == "approved",
                User.is_active.is_(True),
            )
            .limit(1)
        )
        if bootstrap_admin is None:
            raise RuntimeError(
                "No active Admin account exists. Run scripts/create_user.py with "
                "--role admin before startup."
            )

    # Release targets stuck in "Checking" by a previous process, and clean up
    # orphaned staging/artifact files.
    with SessionLocal() as db:
        recover_stale_checks(db, settings)
        reconcile_artifacts(db, settings)

    scheduler: CheckScheduler | None = None
    if settings.SCHEDULER_ENABLED:
        scheduler = CheckScheduler(settings, SessionLocal)
        await scheduler.start()

    yield

    if scheduler is not None:
        await scheduler.stop()


app = FastAPI(
    title=settings.PROJECT_NAME,
    root_path=settings.ROOT_PATH,
    lifespan=lifespan,
)

# Add Rate Limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

origins = settings.cors_origins_list

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _is_trusted_origin(origin: str, request: Request, allowed_origins: list[str]) -> bool:
    if origin in allowed_origins:
        return True

    # Same-origin check for reverse proxy / direct access
    try:
        parsed_origin = urlsplit(origin)
    except Exception:
        return False

    if (
        parsed_origin.scheme.lower() not in {"http", "https"}
        or not parsed_origin.hostname
        or parsed_origin.username is not None
        or parsed_origin.password is not None
        or parsed_origin.path not in {"", "/"}
        or parsed_origin.query
        or parsed_origin.fragment
    ):
        return False

    # Nginx overwrites Host with the external authority. Uvicorn only applies
    # forwarded scheme headers from the explicitly trusted proxy address.
    host_header = request.headers.get("host")
    if not host_header:
        return False

    try:
        parsed_host = urlsplit(f"//{host_header}")
        target_host = (parsed_host.hostname or "").rstrip(".").lower()
        origin_host = parsed_origin.hostname.rstrip(".").lower()
        target_port = (
            parsed_host.port
            if parsed_host.port is not None
            else (443 if request.url.scheme == "https" else 80)
        )
        origin_port = (
            parsed_origin.port
            if parsed_origin.port is not None
            else (443 if parsed_origin.scheme.lower() == "https" else 80)
        )
    except ValueError:
        return False

    if (
        not target_host
        or parsed_host.username is not None
        or parsed_host.password is not None
        or parsed_host.path
        or parsed_host.query
        or parsed_host.fragment
        or target_host != origin_host
        or parsed_origin.scheme.lower() != request.url.scheme.lower()
    ):
        return False
    return target_port == origin_port



@app.middleware("http")
async def csrf_origin_validation(request: Request, call_next):
    # Origin validation for state-changing endpoints
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        origin = request.headers.get("origin")
        if (request.url.path.endswith("/auth/register") and not origin) or (
            origin and not _is_trusted_origin(origin, request, origins)
        ):
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"detail": "CSRF verification failed: untrusted origin"},
            )
    return await call_next(request)


app.include_router(targets.router)
app.include_router(tags.router)
app.include_router(checks.router)
app.include_router(snapshots.router)
app.include_router(review.router)
app.include_router(config.router)
app.include_router(auth.router, prefix="/auth")
app.include_router(members.router)
app.include_router(audit.router)


@app.exception_handler(NotFoundError)
async def not_found_error_handler(request: Request, exc: NotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(ValidationError)
async def validation_error_handler(request: Request, exc: ValidationError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(SsrfBlockedError)
async def ssrf_blocked_error_handler(request: Request, exc: SsrfBlockedError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(DnsResolutionError)
async def dns_resolution_error_handler(request: Request, exc: DnsResolutionError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(InvalidStatusTransitionError)
async def invalid_status_transition_handler(
    request: Request,
    exc: InvalidStatusTransitionError,
) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(ConflictError)
async def conflict_error_handler(request: Request, exc: ConflictError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
