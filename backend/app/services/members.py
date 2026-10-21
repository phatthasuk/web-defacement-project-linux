from typing import Literal

from sqlalchemy import exists, func, or_, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload
from starlette.concurrency import run_in_threadpool

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
from app.schemas.member import (
    MemberCreate,
    MemberRead,
    MemberState,
    MemberUpdate,
    MemberWebsiteRead,
    MemberWebsitesCountsRead,
    MemberWebsitesListRead,
    MemberWebsiteTagRead,
    PaginatedMembersRead,
    PaginatedMemberWebsitesRead,
    RejectMember,
    ResetPassword,
    TargetAssigneeRead,
)


def record_member_audit_event(
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


def get_member_state(user: User) -> MemberState:
    if user.registration_status == "pending":
        return "pending"
    if user.registration_status == "rejected":
        return "rejected"
    return "active" if user.is_active else "suspended"


def get_member_assigned_counts(db: Session, user_ids: list[int]) -> dict[int, int]:
    if not user_ids:
        return {}
    results = db.execute(
        select(UserTargetAssignment.user_id, func.count())
        .select_from(UserTargetAssignment)
        .join(Target, Target.id == UserTargetAssignment.target_id)
        .where(UserTargetAssignment.user_id.in_(user_ids), Target.is_active.is_(True))
        .group_by(UserTargetAssignment.user_id)
    ).all()
    return {uid: int(count) for uid, count in results}


def serialize_member(user: User, assigned_count: int) -> MemberRead:
    return MemberRead(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        role=user.role,
        is_active=user.is_active,
        status=get_member_state(user),
        registration_status=user.registration_status,  # type: ignore[arg-type]
        registration_at=user.created_at,
        registration_reviewed_at=user.registration_reviewed_at,
        registration_reviewed_by=user.registration_reviewed_by,
        registration_rejection_reason=user.registration_rejection_reason,
        last_login_at=user.last_login_at,
        must_change_password=user.must_change_password,
        assigned_website_count=assigned_count,
        created_at=user.created_at,
    )


def build_member_read(db: Session, user: User, assigned_count: int | None = None) -> MemberRead:
    if assigned_count is None:
        counts = get_member_assigned_counts(db, [user.id])
        assigned_count = counts.get(user.id, 0)
    return serialize_member(user, assigned_count)


def list_members(
    db: Session,
    *,
    search: str | None = None,
    member_status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> PaginatedMembersRead:
    statement = select(User)
    if search and search.strip():
        term = f"%{search.strip()}%"
        statement = statement.where(or_(User.username.ilike(term), User.display_name.ilike(term)))
    if member_status in ("pending", "rejected"):
        statement = statement.where(User.registration_status == member_status)
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
    user_ids = [row.id for row in rows]
    counts_by_user = get_member_assigned_counts(db, user_ids)
    items = [serialize_member(row, counts_by_user.get(row.id, 0)) for row in rows]
    return PaginatedMembersRead(
        items=items,
        total=total,
        pending_count=pending_count,
        limit=limit,
        offset=offset,
    )


async def create_member(
    db: Session,
    actor: User,
    payload: MemberCreate,
) -> MemberRead:
    now = utcnow()
    hashed = await run_in_threadpool(get_password_hash, payload.temporary_password)
    member = User(
        username=payload.username,
        display_name=payload.display_name,
        hashed_password=hashed,
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
    record_member_audit_event(
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
    return build_member_read(db, member, assigned_count=0)


def get_member(db: Session, member_id: int) -> MemberRead:
    member = db.get(User, member_id)
    if member is None:
        raise NotFoundError("Member not found")
    return build_member_read(db, member)


def approve_member(db: Session, actor: User, member_id: int) -> MemberRead:
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
    record_member_audit_event(
        db,
        actor,
        "member.approved",
        member_id=member.id,
        before={"registration_status": "pending", "is_active": False},
        after={"registration_status": "approved", "is_active": True},
    )
    db.commit()
    db.refresh(member)
    return build_member_read(db, member)


def reject_member(db: Session, actor: User, member_id: int, payload: RejectMember) -> MemberRead:
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
    record_member_audit_event(
        db,
        actor,
        "member.rejected",
        member_id=member.id,
        before={"registration_status": "pending"},
        after={"registration_status": "rejected", "reason": reason},
    )
    db.commit()
    db.refresh(member)
    return build_member_read(db, member)


def update_member(db: Session, actor: User, member_id: int, payload: MemberUpdate) -> MemberRead:
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
    record_member_audit_event(
        db, actor, "member.updated", member_id=member.id, before=before, after=data
    )
    db.commit()
    db.refresh(member)
    return build_member_read(db, member)


async def reset_member_password(
    db: Session,
    actor: User,
    member_id: int,
    payload: ResetPassword,
) -> None:
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
    record_member_audit_event(
        db,
        actor,
        "member.password_reset",
        member_id=member.id,
        after={"must_change_password": True},
    )
    db.commit()


def list_member_websites(
    db: Session,
    member_id: int,
    *,
    include_inactive: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> MemberWebsitesListRead:
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
    items = [
        MemberWebsiteRead(
            id=t.id,
            name=t.name,
            url=t.url,
            is_active=t.is_active,
            tags=[
                MemberWebsiteTagRead(id=tag.id, name=tag.name, color_key=tag.color_key)
                for tag in t.tags
            ],
            assignees=[],
        )
        for t in targets
    ]
    return MemberWebsitesListRead(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


def assign_website(db: Session, actor: User, member_id: int, target_id: str) -> None:
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
        record_member_audit_event(
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


def remove_website_assignment(db: Session, actor: User, member_id: int, target_id: str) -> None:
    assignment = db.get(UserTargetAssignment, (member_id, target_id))
    if assignment is not None:
        db.delete(assignment)
        record_member_audit_event(
            db,
            actor,
            "assignment.removed",
            member_id=member_id,
            target_id=target_id,
            before={"member_id": member_id, "target_id": target_id},
        )
        db.commit()


def list_assignment_websites(
    db: Session,
    *,
    view: Literal["all", "unassigned", "assigned"] = "all",
    search: str | None = None,
    operator_id: int | None = None,
    tag_ids: list[str] | None = None,
    include_inactive: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> PaginatedMemberWebsitesRead:
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
    # Batch query assignees for all targets in one query instead of querying in a loop
    target_ids = [t.id for t in targets]
    assignees_by_target: dict[str, list[TargetAssigneeRead]] = {tid: [] for tid in target_ids}
    if target_ids:
        assignee_rows = db.execute(
            select(
                UserTargetAssignment.target_id,
                User.id,
                User.username,
                User.display_name,
                User.is_active,
            )
            .join(User, User.id == UserTargetAssignment.user_id)
            .where(
                UserTargetAssignment.target_id.in_(target_ids),
                User.role == "operator",
            )
            .order_by(User.display_name, User.username)
        ).all()
        for tid, uid, uname, dname, is_act in assignee_rows:
            assignees_by_target[tid].append(
                TargetAssigneeRead(
                    id=uid,
                    username=uname,
                    display_name=dname,
                    is_active=is_act,
                )
            )

    items = [
        MemberWebsiteRead(
            id=target.id,
            name=target.name,
            url=target.url,
            is_active=target.is_active,
            tags=[
                MemberWebsiteTagRead(id=t.id, name=t.name, color_key=t.color_key)
                for t in target.tags
            ],
            assignees=assignees_by_target.get(target.id, []),
        )
        for target in targets
    ]
    return PaginatedMemberWebsitesRead(
        items=items,
        total=total,
        counts=MemberWebsitesCountsRead(**counts),
        limit=limit,
        offset=offset,
    )
