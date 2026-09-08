import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.routes import auth, checks, config, review, snapshots, targets
from app.api.routes.auth import limiter
from app.core.config import get_settings
from app.core.errors import ConflictError, NotFoundError, SsrfBlockedError, ValidationError
from app.core.status import InvalidStatusTransitionError
from app.db.session import Base, SessionLocal, engine
from app.models import (  # noqa: F401  (registers tables on Base)
    CheckResult,
    Session,
    Snapshot,
    Target,
    User,
)
from app.services.checks import reconcile_artifacts, recover_stale_checks
from app.services.scheduler import CheckScheduler

settings = get_settings()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Fail closed if production and secure cookies are disabled
    if settings.ENVIRONMENT == "production" and not settings.SESSION_COOKIE_SECURE:
        raise RuntimeError("Production environment must run with SESSION_COOKIE_SECURE=True")
    
    # Create database tables (now mostly handled by alembic, but keeping for compatibility)
    Base.metadata.create_all(bind=engine)
    
    # Create data directories if they don't exist
    os.makedirs(settings.data_dir_path / "screenshots", exist_ok=True)
    os.makedirs(settings.data_dir_path / "text", exist_ok=True)
    os.makedirs(settings.data_dir_path / "html", exist_ok=True)
    os.makedirs(settings.data_dir_path / "staging", exist_ok=True)

    # Release targets stuck in "Checking" by a previous process, and clean up
    # orphaned staging/artifact files.
    with SessionLocal() as db:
        recover_stale_checks(db)
        reconcile_artifacts(db, settings)

    scheduler: CheckScheduler | None = None
    if settings.SCHEDULER_ENABLED:
        scheduler = CheckScheduler(settings, SessionLocal)
        await scheduler.start()

    yield

    if scheduler is not None:
        await scheduler.stop()

app = FastAPI(title=settings.PROJECT_NAME, lifespan=lifespan)

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

@app.middleware("http")
async def csrf_origin_validation(request: Request, call_next):
    # Origin validation for state-changing endpoints
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        origin = request.headers.get("origin")
        if origin and origin not in origins:
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"detail": "CSRF verification failed: untrusted origin"}
            )
    return await call_next(request)

app.include_router(targets.router)
app.include_router(checks.router)
app.include_router(snapshots.router)
app.include_router(review.router)
app.include_router(config.router)
app.include_router(auth.router, prefix="/auth")


@app.exception_handler(NotFoundError)
async def not_found_error_handler(request: Request, exc: NotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(ValidationError)
async def validation_error_handler(request: Request, exc: ValidationError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(SsrfBlockedError)
async def ssrf_blocked_error_handler(request: Request, exc: SsrfBlockedError) -> JSONResponse:
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
