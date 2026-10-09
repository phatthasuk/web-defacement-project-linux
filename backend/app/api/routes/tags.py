from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.models import Tag, Target, TargetTag
from app.schemas import PaginatedTagsRead, TagCreate, TagRead, TagUpdate
from app.schemas.tag import normalize_tag_name

router = APIRouter(prefix="/tags", tags=["tags"], dependencies=[Depends(get_current_user)])
DbSession = Annotated[Session, Depends(get_db)]


def as_tag_read(tag: Tag, target_count: int = 0) -> TagRead:
    return TagRead.model_validate(tag).model_copy(update={"target_count": target_count})


def active_target_count(db: Session, tag_id: str) -> int:
    tag_ids = [tag_id]
    tag_ids.extend(db.scalars(select(Tag.id).where(Tag.parent_id == tag_id)))
    return int(
        db.scalar(
            select(func.count(func.distinct(TargetTag.target_id)))
            .join(Target, Target.id == TargetTag.target_id)
            .where(TargetTag.tag_id.in_(tag_ids), Target.is_active.is_(True))
        )
        or 0
    )


@router.get("", response_model=PaginatedTagsRead)
async def list_tags(
    db: DbSession,
    search: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PaginatedTagsRead:
    statement = select(Tag)
    if search and search.strip():
        normalized_search = normalize_tag_name(search)
        matching_parents = select(Tag.id).where(Tag.normalized_name.contains(normalized_search))
        statement = statement.where(
            Tag.normalized_name.contains(normalized_search)
            | Tag.id.in_(select(Tag.parent_id).where(Tag.normalized_name.contains(normalized_search)))
            | Tag.parent_id.in_(matching_parents)
        )
    total = int(db.scalar(select(func.count()).select_from(statement.subquery())) or 0)
    tags = list(
        db.scalars(statement.order_by(Tag.name.asc(), Tag.id.asc()).limit(limit).offset(offset))
    )
    return PaginatedTagsRead(
        items=[as_tag_read(tag, active_target_count(db, tag.id)) for tag in tags],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=TagRead, status_code=status.HTTP_201_CREATED)
async def create_tag(payload: TagCreate, db: DbSession) -> TagRead:
    _validate_parent(db, payload.parent_id)
    tag = Tag(
        name=payload.name,
        normalized_name=normalize_tag_name(payload.name),
        color_key=payload.color_key,
        parent_id=payload.parent_id,
    )
    db.add(tag)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("A tag with this name already exists") from exc
    db.refresh(tag)
    return as_tag_read(tag)


@router.patch("/{tag_id}", response_model=TagRead)
async def update_tag(tag_id: str, payload: TagUpdate, db: DbSession) -> TagRead:
    tag = db.get(Tag, tag_id)
    if tag is None:
        raise NotFoundError(f"Tag not found: {tag_id}")
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
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("A tag with this name already exists") from exc
    db.refresh(tag)
    return as_tag_read(tag, active_target_count(db, tag.id))


@router.delete("/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tag(tag_id: str, db: DbSession) -> Response:
    tag = db.get(Tag, tag_id)
    if tag is None:
        raise NotFoundError(f"Tag not found: {tag_id}")
    if tag.children:
        raise ConflictError("Delete or move this tag's sub-tags before deleting it")
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
