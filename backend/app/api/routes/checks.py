from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

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
from app.models import CheckResult, Target
from app.schemas import CheckResultRead, CheckTriggerResponse
from app.services.checks import CaptureFunc
from app.services.concurrency import SessionFactory, is_target_in_flight, run_checks_for_targets

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
) -> CheckTriggerResponse:
    target = db.get(Target, target_id)
    if target is None:
        raise NotFoundError(f"Target not found: {target_id}")
    if not target.is_active:
        raise ValidationError("Target is inactive")
    if target.status == STATUS_CHECKING or is_target_in_flight(target_id):
        return CheckTriggerResponse(target_id=target_id, accepted=False)

    background_tasks.add_task(
        run_checks_for_targets,
        [target_id],
        settings,
        capture_func=capture_func,
        session_factory=session_factory,
    )
    return CheckTriggerResponse(target_id=target_id, accepted=True)


@router.get("/checks/{check_id}", response_model=CheckResultRead)
async def get_check_result(check_id: str, db: DbSession) -> CheckResult:
    check_result = db.get(CheckResult, check_id)
    if check_result is None:
        raise NotFoundError(f"CheckResult not found: {check_id}")
    return check_result


@router.get("/targets/{target_id}/checks", response_model=list[CheckResultRead])
async def list_target_check_results(
    target_id: str,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[CheckResult]:
    target = db.get(Target, target_id)
    if target is None:
        raise NotFoundError(f"Target not found: {target_id}")

    return list(
        db.scalars(
            select(CheckResult)
            .where(CheckResult.target_id == target_id)
            .order_by(CheckResult.created_at.desc(), CheckResult.id.desc())
            .limit(limit)
            .offset(offset)
        )
    )
