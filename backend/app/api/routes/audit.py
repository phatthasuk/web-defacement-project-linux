from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.authorization import require_admin
from app.api.deps import get_current_user, get_db
from app.models import MemberAuditEvent, User
from app.schemas.audit import AuditEventRead

router = APIRouter(prefix="/audit-events", tags=["audit"], dependencies=[Depends(get_current_user)])

DbSession = Annotated[Session, Depends(get_db)]


@router.get("", response_model=list[AuditEventRead])
async def list_audit_events(
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
    target_id: str | None = None,
    actor_id: int | None = None,
    action: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[MemberAuditEvent]:
    """Newest first. Admin only: events name who changed what, and when."""
    require_admin(user)
    statement = select(MemberAuditEvent)
    if target_id is not None:
        statement = statement.where(MemberAuditEvent.target_id == target_id)
    if actor_id is not None:
        statement = statement.where(MemberAuditEvent.actor_id == actor_id)
    if action is not None:
        statement = statement.where(MemberAuditEvent.action == action)
    statement = statement.order_by(MemberAuditEvent.occurred_at.desc(), MemberAuditEvent.id.desc())
    return list(db.scalars(statement.limit(limit).offset(offset)))
