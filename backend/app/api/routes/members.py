from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import exists, func, or_, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload
from starlette.concurrency import run_in_threadpool

from app.api.authorization import require_admin
from app.api.deps import get_current_user, get_db
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.security import get_password_hash, verify_password
from app.core.time import utcnow
from app.models import (
    MemberAuditEvent,
    Tag,
    Target,
    User,
    UserTargetAssignment,
)
from app.models import (
    Session as LoginSession,
)
from app.schemas.member import MemberCreate, MemberUpdate, RejectMember, ResetPassword

router = APIRouter(tags=["members"], dependencies=[Depends(get_current_user)])
DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


def _audit(
    db: Session,
    actor: User | None,
    action: str,
    *,
    member_id: int | None = None,
    target_id: str | None = None,
    before: dict | None = None,
    after: dict | None = None,
    source: str = "application",
    details: str | None = None,
) -> None:
    db.add(
        MemberAuditEvent(
            actor_id=actor.id if actor else None,
            action=action,
            member_id=member_id,
            target_id=target_id,
            before=before,
            after=after,
            source=source,
            details=details,
            occurred_at=utcnow(),
        )
    )


def _member_state(user: User) -> str:
    if user.registration_status == "pending":
        return "pending"
    if user.registration_status == "rejected":
        return "rejected"
    return "active" if user.is_active else "suspended"


def _member_read(db: Session, user: User) -> dict:
    assigned_count = (
        db.scalar(
            select(func.count())
            .select_from(UserTargetAssignment)
            .join(Target, Target.id == UserTargetAssignment.target_id)
            .where(UserTargetAssignment.user_id == user.id, Target.is_active.is_(True))
        )
        or 0
    )
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "role": user.role,
        "is_active": user.is_active,
        "status": _member_state(user),
        "registration_status": user.registration_status,
        "registration_at": user.created_at,
        "registration_reviewed_at": user.registration_reviewed_at,
        "registration_reviewed_by": user.registration_reviewed_by,
        "registration_rejection_reason": user.registration_rejection_reason,
        "last_login_at": user.last_login_at,
        "must_change_password": user.must_change_password,
        "assigned_website_count": int(assigned_count),
        "created_at": user.created_at,
    }


@router.get("/members")
async def list_members(
    db: DbSession,
    user: CurrentUser,
    search: str | None = None,
    member_status: Annotated[
        Literal["pending", "active", "suspended", "rejected"] | None, Query(alias="status")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    require_admin(user)
    statement = select(User)
    if search and search.strip():
        term = f"%{search.strip()}%"
        statement = statement.where(or_(User.username.ilike(term), User.display_name.ilike(term)))
    if member_status == "pending":
        statement = statement.where(User.registration_status == "pending")
    elif member_status == "rejected":
        statement = statement.where(User.registration_status == "rejected")
    elif member_status == "active":
        statement = statement.where(
            User.registration_status == "approved", User.is_active.is_(True)
        )
    elif member_status == "suspended":
        statement = statement.where(
            User.registration_status == "approved", User.is_active.is_(False)
        )
    total = int(db.scalar(select(func.count()).select_from(statement.subquery())) or 0)
    pending_count = int(
        db.scalar(
            select(func.count()).select_from(User).where(User.registration_status == "pending")
        )
        or 0
    )
    rows = list(
        db.scalars(
            statement.order_by(User.created_at.desc(), User.id.desc()).limit(limit).offset(offset)
        )
    )
    return {
        "items": [_member_read(db, row) for row in rows],
        "total": total,
        "pending_count": pending_count,
        "limit": limit,
        "offset": offset,
    }


@router.post("/members", status_code=status.HTTP_201_CREATED)
async def create_member(payload: MemberCreate, db: DbSession, actor: CurrentUser) -> dict:
    require_admin(actor)
    now = utcnow()
    member = User(
        username=payload.username,
        display_name=payload.display_name,
        hashed_password=await run_in_threadpool(get_password_hash, payload.temporary_password),
        role="operator",
        registration_status="approved",
        is_active=True,
        must_change_password=True,
        password_changed_at=None,
        created_at=now,
        updated_at=now,
    )
    db.add(member)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("Username is already registered") from exc
    _audit(
        db,
        actor,
        "member.created",
        member_id=member.id,
        after={
            "username": member.username,
            "role": "operator",
            "is_active": True,
            "source": "admin_created",
        },
    )
    db.commit()
    db.refresh(member)
    return _member_read(db, member)


@router.get("/members/{member_id}")
async def get_member(member_id: int, db: DbSession, actor: CurrentUser) -> dict:
    require_admin(actor)
    member = db.get(User, member_id)
    if member is None:
        raise NotFoundError("Member not found")
    return _member_read(db, member)


@router.post("/members/{member_id}/approve")
async def approve_member(member_id: int, db: DbSession, actor: CurrentUser) -> dict:
    require_admin(actor)
    now = utcnow()
    result = db.execute(
        update(User)
        .where(
            User.id == member_id,
            User.registration_status == "pending",
            User.role == "operator",
        )
        .values(
            registration_status="approved",
            is_active=True,
            registration_reviewed_by=actor.id,
            registration_reviewed_at=now,
            updated_at=now,
        )
    )
    member = db.get(User, member_id)
    if member is None:
        db.rollback()
        raise NotFoundError("Member not found")
    if result.rowcount != 1:
        db.rollback()
        raise ConflictError("Only pending Operator registrations can be approved")
    _audit(
        db,
        actor,
        "member.approved",
        member_id=member.id,
        before={"registration_status": "pending", "is_active": False},
        after={"registration_status": "approved", "is_active": True},
    )
    db.commit()
    return _member_read(db, member)


@router.post("/members/{member_id}/reject")
async def reject_member(
    member_id: int, payload: RejectMember, db: DbSession, actor: CurrentUser
) -> dict:
    require_admin(actor)
    now = utcnow()
    reason = payload.reason.strip() if payload.reason else None
    result = db.execute(
        update(User)
        .where(
            User.id == member_id,
            User.registration_status == "pending",
            User.role == "operator",
        )
        .values(
            registration_status="rejected",
            is_active=False,
            registration_reviewed_by=actor.id,
            registration_reviewed_at=now,
            registration_rejection_reason=reason,
            updated_at=now,
        )
    )
    member = db.get(User, member_id)
    if member is None:
        db.rollback()
        raise NotFoundError("Member not found")
    if result.rowcount != 1:
        db.rollback()
        raise ConflictError("Only pending Operator registrations can be rejected")
    db.query(LoginSession).filter(
        LoginSession.user_id == member.id, LoginSession.revoked_at.is_(None)
    ).update(
        {LoginSession.revoked_at: now, LoginSession.revocation_reason: "registration_rejected"},
        synchronize_session=False,
    )
    _audit(
        db,
        actor,
        "member.rejected",
        member_id=member.id,
        before={"registration_status": "pending"},
        after={"registration_status": "rejected", "reason": reason},
    )
    db.commit()
    return _member_read(db, member)


@router.patch("/members/{member_id}")
async def update_member(
    member_id: int, payload: MemberUpdate, db: DbSession, actor: CurrentUser
) -> dict:
    require_admin(actor)
    member = db.scalar(select(User).where(User.id == member_id).with_for_update())
    if member is None:
        raise NotFoundError("Member not found")
    data = payload.model_dump(exclude_unset=True)
    if member.registration_status != "approved" and data.get("is_active") is True:
        raise ConflictError("Pending or rejected registrations cannot be enabled")
    before = {key: getattr(member, key) for key in data}
    now = utcnow()
    suspend_admin = data.get("is_active") is False and member.role == "admin" and member.is_active
    for key, value in data.items():
        if key != "is_active" or not suspend_admin:
            setattr(member, key, value)
    if suspend_admin:
        active_admin_count = (
            select(func.count())
            .select_from(User)
            .where(
                User.role == "admin",
                User.registration_status == "approved",
                User.is_active.is_(True),
            )
            .scalar_subquery()
        )
        result = db.execute(
            update(User)
            .where(
                User.id == member.id,
                User.role == "admin",
                User.registration_status == "approved",
                User.is_active.is_(True),
                active_admin_count > 1,
            )
            .values(is_active=False, updated_at=now)
        )
        if result.rowcount != 1:
            db.rollback()
            raise ConflictError("Cannot suspend the last active Admin")
        member.is_active = False
    if data.get("is_active") is False:
        db.query(LoginSession).filter(
            LoginSession.user_id == member.id, LoginSession.revoked_at.is_(None)
        ).update(
            {LoginSession.revoked_at: now, LoginSession.revocation_reason: "account_suspended"},
            synchronize_session=False,
        )
    _audit(db, actor, "member.updated", member_id=member.id, before=before, after=data)
    db.commit()
    return _member_read(db, member)


@router.post("/members/{member_id}/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(member_id: int, payload: ResetPassword, db: DbSession, actor: CurrentUser):
    require_admin(actor)
    member = db.get(User, member_id)
    if member is None:
        raise NotFoundError("Member not found")
    if member.role != "operator" or member.registration_status != "approved":
        raise ConflictError("Password reset is available for approved Operators only")
    same_password = await run_in_threadpool(
        verify_password, payload.temporary_password, member.hashed_password
    )
    if same_password:
        raise ValidationError("Choose a different temporary password")
    member.hashed_password = await run_in_threadpool(
        get_password_hash, payload.temporary_password
    )
    member.must_change_password = True
    member.password_changed_at = None
    member.failed_login_count = 0
    member.first_failed_login_at = None
    member.locked_until = None
    now = utcnow()
    db.query(LoginSession).filter(
        LoginSession.user_id == member.id, LoginSession.revoked_at.is_(None)
    ).update(
        {LoginSession.revoked_at: now, LoginSession.revocation_reason: "password_reset"},
        synchronize_session=False,
    )
    _audit(
        db,
        actor,
        "member.password_reset",
        member_id=member.id,
        after={"must_change_password": True},
    )
    db.commit()


@router.get("/members/{member_id}/websites")
async def list_member_websites(
    member_id: int,
    db: DbSession,
    actor: CurrentUser,
    include_inactive: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    require_admin(actor)
    member = db.get(User, member_id)
    if member is None:
        raise NotFoundError("Member not found")
    stmt = (
        select(Target)
        .join(UserTargetAssignment, UserTargetAssignment.target_id == Target.id)
        .where(UserTargetAssignment.user_id == member_id)
    )
    if not include_inactive:
        stmt = stmt.where(Target.is_active.is_(True))
    total = int(db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    targets = list(
        db.scalars(
            stmt.options(selectinload(Target.tags))
            .order_by(Target.name)
            .limit(limit)
            .offset(offset)
        )
    )
    return {
        "items": [
            {
                "id": t.id,
                "name": t.name,
                "url": t.url,
                "is_active": t.is_active,
                "tags": [
                    {"id": tag.id, "name": tag.name, "color_key": tag.color_key} for tag in t.tags
                ],
            }
            for t in targets
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.put("/members/{member_id}/websites/{target_id}", status_code=status.HTTP_204_NO_CONTENT)
async def assign_website(member_id: int, target_id: str, db: DbSession, actor: CurrentUser):
    require_admin(actor)
    member = db.get(User, member_id)
    target = db.get(Target, target_id)
    if member is None or target is None:
        raise NotFoundError("Member or website not found")
    if member.role != "operator" or member.registration_status != "approved":
        raise ConflictError("Only approved Operators can be assigned websites")
    created = False
    if db.bind is not None and db.bind.dialect.name == "sqlite":
        result = db.execute(
            sqlite_insert(UserTargetAssignment)
            .values(user_id=member_id, target_id=target_id, assigned_at=utcnow())
            .on_conflict_do_nothing(index_elements=["user_id", "target_id"])
        )
        created = result.rowcount == 1
    elif db.get(UserTargetAssignment, (member_id, target_id)) is None:
        db.add(UserTargetAssignment(user_id=member_id, target_id=target_id, assigned_at=utcnow()))
        created = True
    if created:
        _audit(
            db,
            actor,
            "assignment.created",
            member_id=member_id,
            target_id=target_id,
            after={
                "member_id": member_id,
                "target_id": target_id,
                "member_active": member.is_active,
            },
        )
    db.commit()


@router.delete("/members/{member_id}/websites/{target_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_website_assignment(
    member_id: int, target_id: str, db: DbSession, actor: CurrentUser
):
    require_admin(actor)
    assignment = db.get(UserTargetAssignment, (member_id, target_id))
    if assignment is not None:
        db.delete(assignment)
        _audit(
            db,
            actor,
            "assignment.removed",
            member_id=member_id,
            target_id=target_id,
            before={"member_id": member_id, "target_id": target_id},
        )
        db.commit()


@router.get("/member-assignments/websites")
async def list_assignment_websites(
    db: DbSession,
    actor: CurrentUser,
    view: Literal["all", "unassigned", "assigned"] = "all",
    search: str | None = None,
    operator_id: int | None = None,
    tag_ids: Annotated[list[str] | None, Query()] = None,
    include_inactive: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    require_admin(actor)
    stmt = select(Target)
    if not include_inactive:
        stmt = stmt.where(Target.is_active.is_(True))
    if search and search.strip():
        term = f"%{search.strip()}%"
        stmt = stmt.where(or_(Target.name.ilike(term), Target.url.ilike(term)))
    if tag_ids:
        stmt = stmt.where(
            Target.tags.any(Tag.id.in_(tag_ids)) | Target.tags.any(Tag.parent_id.in_(tag_ids))
        )
    assignee_exists = exists(
        select(UserTargetAssignment.user_id)
        .join(User, User.id == UserTargetAssignment.user_id)
        .where(
            UserTargetAssignment.target_id == Target.id,
            User.role == "operator",
            User.registration_status == "approved",
            User.is_active.is_(True),
        )
    )
    if operator_id is not None:
        operator = db.get(User, operator_id)
        if operator is None or operator.role != "operator":
            raise NotFoundError("Operator not found")
        assigned = exists(
            select(UserTargetAssignment.user_id).where(
                UserTargetAssignment.target_id == Target.id,
                UserTargetAssignment.user_id == operator_id,
            )
        )
        all_base = stmt.where(assigned)
        unassigned_base = stmt.where(~assigned)
        assigned_base = all_base
    else:
        all_base = stmt
        unassigned_base = stmt.where(~assignee_exists)
        assigned_base = stmt.where(assignee_exists)
    counts = {
        "all": int(db.scalar(select(func.count()).select_from(all_base.subquery())) or 0),
        "unassigned": int(
            db.scalar(select(func.count()).select_from(unassigned_base.subquery())) or 0
        ),
        "assigned": int(db.scalar(select(func.count()).select_from(assigned_base.subquery())) or 0),
    }
    selected = {"all": all_base, "unassigned": unassigned_base, "assigned": assigned_base}[view]
    total = counts[view]
    targets = list(
        db.scalars(
            selected.options(selectinload(Target.tags))
            .order_by(Target.name)
            .limit(limit)
            .offset(offset)
        )
    )
    items = []
    for target in targets:
        assignees = list(
            db.execute(
                select(User.id, User.username, User.display_name, User.is_active)
                .join(UserTargetAssignment, UserTargetAssignment.user_id == User.id)
                .where(UserTargetAssignment.target_id == target.id, User.role == "operator")
                .order_by(User.display_name, User.username)
            )
        )
        items.append(
            {
                "id": target.id,
                "name": target.name,
                "url": target.url,
                "is_active": target.is_active,
                "tags": [
                    {"id": t.id, "name": t.name, "color_key": t.color_key} for t in target.tags
                ],
                "assignees": [
                    {
                        "id": a.id,
                        "username": a.username,
                        "display_name": a.display_name,
                        "is_active": a.is_active,
                    }
                    for a in assignees
                ],
            }
        )
    return {"items": items, "total": total, "counts": counts, "limit": limit, "offset": offset}
