from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user, get_db, get_settings
from app.core.config import Settings
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.ssrf_guard import validate_url
from app.core.status import STATUS_AWAITING_BASELINE, STATUS_CHECKING
from app.models import Snapshot, Tag, Target
from app.schemas import PaginatedTargetsRead, SnapshotRead, TargetCreate, TargetRead, TargetUpdate
from app.services.concurrency import is_target_in_flight

router = APIRouter(prefix="/targets", tags=["targets"], dependencies=[Depends(get_current_user)])

DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]


@router.post("", response_model=TargetRead, status_code=201)
async def create_target(
    payload: TargetCreate,
    db: DbSession,
    settings: AppSettings,
) -> Target:
    validate_url(payload.url, settings)
    tags = _resolve_tags(db, payload.tag_ids)
    target = Target(
        name=payload.name,
        url=payload.url,
        allowed_domains=payload.allowed_domains,
        tags=tags,
    )
    db.add(target)
    db.commit()
    db.refresh(target)
    return target


@router.get("", response_model=list[TargetRead])
async def list_targets(
    db: DbSession,
    include_inactive: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    tag_ids: Annotated[list[str] | None, Query()] = None,
    tag_match: Annotated[str, Query(pattern="^(any|all)$")] = "any",
) -> list[Target]:
    statement = _apply_tag_filter(select(Target), tag_ids, tag_match).options(
        selectinload(Target.tags)
    )
    statement = statement.order_by(Target.created_at.desc())
    if not include_inactive:
        statement = statement.where(Target.is_active.is_(True))
    statement = statement.limit(limit).offset(offset)
    return list(db.scalars(statement))


@router.get("/page", response_model=PaginatedTargetsRead)
async def list_paginated_targets(
    db: DbSession,
    include_inactive: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    tag_ids: Annotated[list[str] | None, Query()] = None,
    tag_match: Annotated[str, Query(pattern="^(any|all)$")] = "any",
) -> PaginatedTargetsRead:
    base_query = _apply_tag_filter(select(Target), tag_ids, tag_match)
    if not include_inactive:
        base_query = base_query.where(Target.is_active.is_(True))

    total = db.scalar(select(func.count()).select_from(base_query.subquery())) or 0

    items_stmt = (
        base_query.order_by(Target.created_at.desc(), Target.id.desc())
        .options(selectinload(Target.tags))
        .limit(limit)
        .offset(offset)
    )
    targets = list(db.scalars(items_stmt))

    return PaginatedTargetsRead(
        items=[TargetRead.model_validate(t) for t in targets],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{target_id}", response_model=TargetRead)
async def get_target(target_id: str, db: DbSession) -> Target:
    target = db.scalar(
        select(Target).where(Target.id == target_id).options(selectinload(Target.tags))
    )
    if target is None:
        raise NotFoundError(f"Target not found: {target_id}")
    return target


@router.patch("/{target_id}", response_model=TargetRead)
async def update_target(
    target_id: str,
    payload: TargetUpdate,
    db: DbSession,
    settings: AppSettings,
) -> Target:
    target = db.get(Target, target_id)
    if target is None:
        raise NotFoundError(f"Target not found: {target_id}")

    update_data = payload.model_dump(exclude_unset=True)
    if "name" in update_data:
        target.name = update_data["name"]
    if "url" in update_data:
        new_url = update_data["url"]
        if new_url != target.url:
            if target.status == STATUS_CHECKING or is_target_in_flight(target_id):
                raise ConflictError(
                    "Target is currently being checked. "
                    "URL cannot be modified until the check finishes."
                )
            validate_url(new_url, settings)
            has_history = db.scalar(
                select(Snapshot.id).where(Snapshot.target_id == target_id).limit(1)
            ) is not None
            target.url = new_url
            if has_history:
                target.url_revision += 1
                target.status = STATUS_AWAITING_BASELINE
                target.last_error = None
    if "is_active" in update_data:
        target.is_active = update_data["is_active"]
    if "allowed_domains" in update_data:
        target.allowed_domains = update_data["allowed_domains"]
    if "tag_ids" in update_data:
        target.tags = _resolve_tags(db, update_data["tag_ids"])
        target.updated_at = datetime.now(UTC)

    db.commit()
    db.refresh(target)
    return target


def _resolve_tags(db: Session, tag_ids: list[str]) -> list[Tag]:
    if not tag_ids:
        return []
    tags = list(db.scalars(select(Tag).where(Tag.id.in_(tag_ids))))
    if len(tags) != len(tag_ids):
        found_ids = {tag.id for tag in tags}
        missing_ids = [tag_id for tag_id in tag_ids if tag_id not in found_ids]
        raise ValidationError(f"Tag not found: {', '.join(missing_ids)}")
    by_id = {tag.id: tag for tag in tags}
    return [by_id[tag_id] for tag_id in tag_ids]


def _apply_tag_filter(statement, tag_ids: list[str] | None, tag_match: str):
    if not tag_ids:
        return statement
    if tag_match == "all":
        return statement.where(and_(*(Target.tags.any(Tag.id == tag_id) for tag_id in tag_ids)))
    return statement.where(Target.tags.any(Tag.id.in_(tag_ids)))


@router.delete("/{target_id}", response_model=TargetRead)
async def delete_target(target_id: str, db: DbSession) -> Target:
    target = db.get(Target, target_id)
    if target is None:
        raise NotFoundError(f"Target not found: {target_id}")

    target.is_active = False
    db.commit()
    db.refresh(target)
    return target


@router.get("/{target_id}/snapshots", response_model=list[SnapshotRead])
async def list_target_snapshots(
    target_id: str,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    include_history: bool = False,
) -> list[Snapshot]:
    target = db.get(Target, target_id)
    if target is None:
        raise NotFoundError(f"Target not found: {target_id}")

    statement = select(Snapshot).where(Snapshot.target_id == target_id)
    if not include_history:
        statement = statement.where(Snapshot.url_revision == target.url_revision)
    return list(
        db.scalars(
            statement.order_by(Snapshot.captured_at.desc(), Snapshot.id.desc())
            .limit(limit)
            .offset(offset)
        )
    )


@router.get("/{target_id}/baseline", response_model=SnapshotRead | None)
async def get_target_baseline_snapshot(
    target_id: str,
    db: DbSession,
) -> Snapshot | None:
    target = db.get(Target, target_id)
    if target is None:
        raise NotFoundError(f"Target not found: {target_id}")

    return db.scalar(
        select(Snapshot)
        .where(
            Snapshot.target_id == target_id,
            Snapshot.url_revision == target.url_revision,
            Snapshot.is_baseline.is_(True),
        )
        .order_by(Snapshot.captured_at.desc(), Snapshot.id.desc())
    )


@router.get("/{target_id}/baselines", response_model=list[SnapshotRead])
async def list_target_baselines(
    target_id: str,
    db: DbSession,
) -> list[Snapshot]:
    target = db.get(Target, target_id)
    if target is None:
        raise NotFoundError(f"Target not found: {target_id}")

    return list(
        db.scalars(
            select(Snapshot)
            .where(
                Snapshot.target_id == target_id,
                Snapshot.url_revision == target.url_revision,
                Snapshot.is_baseline.is_(True),
            )
            .order_by(Snapshot.captured_at.desc(), Snapshot.id.desc())
        )
    )


@router.post("/{target_id}/baselines/{snapshot_id}/demote", response_model=SnapshotRead)
async def demote_target_baseline(
    target_id: str,
    snapshot_id: str,
    db: DbSession,
) -> Snapshot:
    target = db.get(Target, target_id)
    if target is None:
        raise NotFoundError(f"Target not found: {target_id}")

    if target.status == STATUS_CHECKING or is_target_in_flight(target_id):
        raise ConflictError("Cannot demote baseline while check is in progress")

    snapshot = db.get(Snapshot, snapshot_id)
    if (
        snapshot is None
        or snapshot.target_id != target_id
        or snapshot.url_revision != target.url_revision
    ):
        raise NotFoundError(f"Snapshot not found for target {target_id}: {snapshot_id}")

    if not snapshot.is_baseline:
        raise ValidationError(f"Snapshot {snapshot_id} is not an active baseline")

    # Refuse to remove the last baseline. With none left, the next check takes the
    # `baseline is None` path in run_target_check, which adopts whatever the site
    # is serving at that moment as the new baseline and reports OK without a
    # CheckResult. If the site were defaced at that point the defacement would
    # become the reference silently — the exact failure mode described in
    # plan/archive/auto-rebaseline.md. To replace the only baseline, approve the
    # new one first, then demote the old one.
    remaining = (
        db.scalar(
            select(func.count())
            .select_from(Snapshot)
            .where(
                Snapshot.target_id == target_id,
                Snapshot.url_revision == target.url_revision,
                Snapshot.is_baseline.is_(True),
                Snapshot.id != snapshot_id,
            )
        )
        or 0
    )
    if remaining == 0:
        raise ValidationError(
            "Cannot remove the only baseline for this target. Approve another "
            "snapshot as a baseline first, otherwise the next check would adopt "
            "the live page as the new baseline without review."
        )

    snapshot.is_baseline = False
    db.commit()
    db.refresh(snapshot)
    return snapshot

