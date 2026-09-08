from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.schemas import BaselineApproveRequest, CheckResultRead, SnapshotRead
from app.services.review import acknowledge_check_result, approve_baseline, confirm_defacement

router = APIRouter(tags=["review"], dependencies=[Depends(get_current_user)])

DbSession = Annotated[Session, Depends(get_db)]


@router.post("/targets/{target_id}/baseline/approve", response_model=SnapshotRead)
async def approve_target_baseline(
    target_id: str,
    payload: BaselineApproveRequest,
    db: DbSession,
) -> object:
    return approve_baseline(db, target_id, payload.snapshot_id)


@router.post("/checks/{check_id}/ack", response_model=CheckResultRead)
async def acknowledge_check(check_id: str, db: DbSession) -> object:
    return acknowledge_check_result(db, check_id)


@router.post("/checks/{check_id}/confirm-defaced", response_model=CheckResultRead)
async def confirm_defaced_check(check_id: str, db: DbSession) -> object:
    return confirm_defacement(db, check_id)
