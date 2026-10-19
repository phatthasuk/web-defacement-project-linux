import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.authorization import require_target_access
from app.api.deps import (
    get_capture_func,
    get_current_user,
    get_db,
    get_session_factory,
    get_settings,
)
from app.core.config import Settings
from app.core.errors import NotFoundError, ValidationError
from app.core.status import STATUS_CHECKING
from app.models import CheckAttempt, CheckResult, Snapshot, User
from app.schemas import CheckAttemptRead, CheckResultRead, CheckTriggerResponse
from app.services.attempts import run_check_attempt
from app.services.checks import CaptureFunc
from app.services.concurrency import (
    SessionFactory,
    release_in_flight,
    try_acquire_in_flight,
)

router = APIRouter(tags=["checks"], dependencies=[Depends(get_current_user)])

DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]
InjectedCaptureFunc = Annotated[CaptureFunc, Depends(get_capture_func)]
InjectedSessionFactory = Annotated[SessionFactory, Depends(get_session_factory)]


@router.post("/targets/{target_id}/check", response_model=CheckTriggerResponse, status_code=202)
async def trigger_target_check(
    target_id: str,
    background_tasks: BackgroundTasks,
    db: DbSession,
    settings: AppSettings,
    capture_func: InjectedCaptureFunc,
    session_factory: InjectedSessionFactory,
    user: Annotated[User, Depends(get_current_user)],
) -> CheckTriggerResponse:
    target = require_target_access(db, user, target_id)
    if not target.is_active:
        raise ValidationError("Target is inactive")
    if target.status == STATUS_CHECKING or not try_acquire_in_flight(target_id):
        return CheckTriggerResponse(target_id=target_id, accepted=False)

    run_id = str(uuid.uuid4())
    try:
        target.check_run_id = run_id
        target.check_run_source = "manual"
        target.check_attempt_count = 0
        target.next_check_at = None
        db.commit()
        background_tasks.add_task(
            run_check_attempt,
            target_id,
            settings,
            run_id=run_id,
            initial_source="manual",
            capture_func=capture_func,
            session_factory=session_factory,
            actor_id=user.id,
        )
    except Exception:
        release_in_flight(target_id)
        raise
    return CheckTriggerResponse(target_id=target_id, accepted=True)


@router.get("/checks/{check_id}", response_model=CheckResultRead)
async def get_check_result(
    check_id: str, db: DbSession, user: Annotated[User, Depends(get_current_user)]
) -> CheckResult:
    check_result = db.get(CheckResult, check_id)
    if check_result is None:
        raise NotFoundError(f"CheckResult not found: {check_id}")
    require_target_access(db, user, check_result.target_id)
    return check_result


@router.get("/targets/{target_id}/checks", response_model=list[CheckResultRead])
async def list_target_check_results(
    target_id: str,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    include_history: bool = False,
) -> list[CheckResult]:
    target = require_target_access(db, user, target_id)

    statement = select(CheckResult).where(CheckResult.target_id == target_id)
    if not include_history:
        statement = statement.where(
            CheckResult.current_snapshot_id.in_(
                select(Snapshot.id).where(
                    Snapshot.target_id == target_id,
                    Snapshot.url_revision == target.url_revision,
                )
            )
        )
    return list(
        db.scalars(
            statement.order_by(CheckResult.created_at.desc(), CheckResult.id.desc())
            .limit(limit)
            .offset(offset)
        )
    )


@router.get(
    "/targets/{target_id}/check-attempts",
    response_model=list[CheckAttemptRead],
)
async def list_target_check_attempts(
    target_id: str,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
    limit: Annotated[int, Query(ge=1, le=200)] = 20,
) -> list[CheckAttempt]:
    require_target_access(db, user, target_id)
    return list(
        db.scalars(
            select(CheckAttempt)
            .where(CheckAttempt.target_id == target_id)
            .order_by(CheckAttempt.started_at.desc(), CheckAttempt.id.desc())
            .limit(limit)
        )
    )
