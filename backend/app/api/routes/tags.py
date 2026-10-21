from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.authorization import require_admin
from app.api.deps import get_current_user, get_db
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.time import utcnow
from app.models import MemberAuditEvent, Tag, Target, TargetTag, User, UserTargetAssignment
from app.schemas import PaginatedTagsRead, TagCreate, TagRead, TagUpdate
from app.schemas.tag import normalize_tag_name

router = APIRouter(prefix="/tags", tags=["tags"], dependencies=[Depends(get_current_user)])
DbSession = Annotated[Session, Depends(get_db)]


def as_tag_read(tag: Tag, target_count: int = 0) -> TagRead:
    return TagRead.model_validate(tag).model_copy(update={"target_count": target_count})


def batch_active_target_counts(db: Session, tag_ids: list[str], user: User) -> dict[str, int]:
    if not tag_ids:
        return {}
    children = db.execute(select(Tag.id, Tag.parent_id).where(Tag.parent_id.in_(tag_ids))).all()
    tag_family: dict[str, set[str]] = {tid: {tid} for tid in tag_ids}
    all_relevant_tag_ids: set[str] = set(tag_ids)
    for child_id, parent_id in children:
        if parent_id in tag_family:
            tag_family[parent_id].add(child_id)
        all_relevant_tag_ids.add(child_id)

    statement = (
        select(TargetTag.tag_id, TargetTag.target_id)
        .join(Target, Target.id == TargetTag.target_id)
        .where(TargetTag.tag_id.in_(all_relevant_tag_ids), Target.is_active.is_(True))
    )
    if user.role == "operator":
        statement = statement.join(
            UserTargetAssignment, UserTargetAssignment.target_id == Target.id
        ).where(UserTargetAssignment.user_id == user.id)

    pairs = db.execute(statement).all()
    targets_by_tag: dict[str, set[str]] = {}
    for tag_id, target_id in pairs:
        if tag_id not in targets_by_tag:
            targets_by_tag[tag_id] = set()
        targets_by_tag[tag_id].add(target_id)

    counts: dict[str, int] = {}
    for tid in tag_ids:
        matched: set[str] = set()
        for family_tid in tag_family[tid]:
            if family_tid in targets_by_tag:
                matched.update(targets_by_tag[family_tid])
        counts[tid] = len(matched)
    return counts


def active_target_count(db: Session, tag_id: str, user: User) -> int:
    return batch_active_target_counts(db, [tag_id], user).get(tag_id, 0)


@router.get("", response_model=PaginatedTagsRead)
async def list_tags(
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
    search: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PaginatedTagsRead:
    statement = select(Tag)
    if user.role == "operator":
        scoped_tag_ids = (
            select(TargetTag.tag_id)
            .join(UserTargetAssignment, UserTargetAssignment.target_id == TargetTag.target_id)
            .where(UserTargetAssignment.user_id == user.id)
        )
        statement = statement.where(
            Tag.id.in_(scoped_tag_ids)
            | Tag.id.in_(select(Tag.parent_id).where(Tag.id.in_(scoped_tag_ids)))
        )
    if search and search.strip():
        normalized_search = normalize_tag_name(search)
        matching_parents = select(Tag.id).where(Tag.normalized_name.contains(normalized_search))
        matching_children = select(Tag.parent_id).where(
            Tag.normalized_name.contains(normalized_search)
        )
        statement = statement.where(
            Tag.normalized_name.contains(normalized_search)
            | Tag.id.in_(matching_children)
            | Tag.parent_id.in_(matching_parents)
        )
    total = int(db.scalar(select(func.count()).select_from(statement.subquery())) or 0)
    tags = list(
        db.scalars(statement.order_by(Tag.name.asc(), Tag.id.asc()).limit(limit).offset(offset))
    )
    tag_ids = [tag.id for tag in tags]
    counts_by_tag = batch_active_target_counts(db, tag_ids, user)
    return PaginatedTagsRead(
        items=[as_tag_read(tag, counts_by_tag.get(tag.id, 0)) for tag in tags],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=TagRead, status_code=status.HTTP_201_CREATED)
async def create_tag(
    payload: TagCreate, db: DbSession, user: Annotated[User, Depends(get_current_user)]
) -> TagRead:
    require_admin(user)
    _validate_parent(db, payload.parent_id)
    tag = Tag(
        name=payload.name,
        normalized_name=normalize_tag_name(payload.name),
        color_key=payload.color_key,
        parent_id=payload.parent_id,
    )
    db.add(tag)
    try:
        db.flush()
        db.add(
            MemberAuditEvent(
                actor_id=user.id,
                action="tag.created",
                after={"tag_id": tag.id, "name": tag.name, "parent_id": tag.parent_id},
                occurred_at=utcnow(),
            )
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("A tag with this name already exists") from exc
    db.refresh(tag)
    return as_tag_read(tag)


@router.patch("/{tag_id}", response_model=TagRead)
async def update_tag(
    tag_id: str, payload: TagUpdate, db: DbSession, user: Annotated[User, Depends(get_current_user)]
) -> TagRead:
    require_admin(user)
    tag = db.get(Tag, tag_id)
    if tag is None:
        raise NotFoundError(f"Tag not found: {tag_id}")
    before = {"name": tag.name, "color_key": tag.color_key, "parent_id": tag.parent_id}
    if payload.name is not None:
        tag.name = payload.name
        tag.normalized_name = normalize_tag_name(payload.name)
    if payload.color_key is not None:
        tag.color_key = payload.color_key
    if "parent_id" in payload.model_fields_set:
        if payload.parent_id != tag.parent_id and tag.children:
            raise ConflictError("A tag with sub-tags cannot be moved")
        if payload.parent_id != tag.parent_id:
            _validate_parent(db, payload.parent_id, current_tag_id=tag_id)
        tag.parent_id = payload.parent_id
    try:
        db.add(
            MemberAuditEvent(
                actor_id=user.id,
                action="tag.updated",
                after={
                    "tag_id": tag.id,
                    "name": tag.name,
                    "color_key": tag.color_key,
                    "parent_id": tag.parent_id,
                },
                before=before,
                occurred_at=utcnow(),
            )
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("A tag with this name already exists") from exc
    db.refresh(tag)
    return as_tag_read(tag, active_target_count(db, tag.id, user))


@router.delete("/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tag(
    tag_id: str, db: DbSession, user: Annotated[User, Depends(get_current_user)]
) -> Response:
    require_admin(user)
    tag = db.get(Tag, tag_id)
    if tag is None:
        raise NotFoundError(f"Tag not found: {tag_id}")
    if tag.children:
        raise ConflictError("Delete or move this tag's sub-tags before deleting it")
    before = {"tag_id": tag.id, "name": tag.name, "parent_id": tag.parent_id}
    db.add(
        MemberAuditEvent(
            actor_id=user.id, action="tag.deleted", before=before, occurred_at=utcnow()
        )
    )
    db.delete(tag)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _validate_parent(db: Session, parent_id: str | None, current_tag_id: str | None = None) -> None:
    if parent_id is None:
        return
    if parent_id == current_tag_id:
        raise ValidationError("A tag cannot be its own parent")
    parent = db.get(Tag, parent_id)
    if parent is None:
        raise NotFoundError(f"Parent tag not found: {parent_id}")
    if parent.parent_id is not None:
        raise ValidationError("Sub-tags cannot have their own sub-tags")
    if current_tag_id and db.scalar(select(Tag.id).where(Tag.parent_id == current_tag_id).limit(1)):
        raise ConflictError("A tag with sub-tags cannot be moved")
