from fastapi import HTTPException, status
from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models import Target, User, UserTargetAssignment


def require_admin(user: User) -> None:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")


def accessible_targets(statement, user: User):
    if user.role == "admin":
        return statement
    if user.role != "operator":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid account role")
    return statement.where(
        exists(
            select(UserTargetAssignment.user_id).where(
                UserTargetAssignment.user_id == user.id,
                UserTargetAssignment.target_id == Target.id,
            )
        )
    )


def require_target_access(db: Session, user: User, target_id: str) -> Target:
    query = accessible_targets(select(Target).where(Target.id == target_id), user)
    target = db.scalar(query)
    if target is None:
        raise NotFoundError("Target not found")
    return target
