from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, status

from app.api.authorization import require_admin
from app.api.deps import get_current_user, get_db
from app.models import User
from app.schemas.member import (
    MemberCreate,
    MemberRead,
    MemberState,
    MemberUpdate,
    MemberWebsitesListRead,
    PaginatedMembersRead,
    PaginatedMemberWebsitesRead,
    RejectMember,
    ResetPassword,
)
from app.services import members as member_service

router = APIRouter(tags=["members"], dependencies=[Depends(get_current_user)])
DbSession = Annotated[member_service.Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


@router.get("/members", response_model=PaginatedMembersRead)
async def list_members(
    db: DbSession,
    user: CurrentUser,
    search: str | None = None,
    member_status: Annotated[MemberState | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PaginatedMembersRead:
    require_admin(user)
    return member_service.list_members(
        db,
        search=search,
        member_status=member_status,
        limit=limit,
        offset=offset,
    )


@router.post("/members", response_model=MemberRead, status_code=status.HTTP_201_CREATED)
async def create_member(
    payload: MemberCreate,
    db: DbSession,
    actor: CurrentUser,
) -> MemberRead:
    require_admin(actor)
    return await member_service.create_member(db, actor, payload)


@router.get("/members/{member_id}", response_model=MemberRead)
async def get_member(
    member_id: int,
    db: DbSession,
    actor: CurrentUser,
) -> MemberRead:
    require_admin(actor)
    return member_service.get_member(db, member_id)


@router.post("/members/{member_id}/approve", response_model=MemberRead)
async def approve_member(
    member_id: int,
    db: DbSession,
    actor: CurrentUser,
) -> MemberRead:
    require_admin(actor)
    return member_service.approve_member(db, actor, member_id)


@router.post("/members/{member_id}/reject", response_model=MemberRead)
async def reject_member(
    member_id: int,
    payload: RejectMember,
    db: DbSession,
    actor: CurrentUser,
) -> MemberRead:
    require_admin(actor)
    return member_service.reject_member(db, actor, member_id, payload)


@router.patch("/members/{member_id}", response_model=MemberRead)
async def update_member(
    member_id: int,
    payload: MemberUpdate,
    db: DbSession,
    actor: CurrentUser,
) -> MemberRead:
    require_admin(actor)
    return member_service.update_member(db, actor, member_id, payload)


@router.post("/members/{member_id}/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(
    member_id: int,
    payload: ResetPassword,
    db: DbSession,
    actor: CurrentUser,
) -> None:
    require_admin(actor)
    await member_service.reset_member_password(db, actor, member_id, payload)


@router.get("/members/{member_id}/websites", response_model=MemberWebsitesListRead)
async def list_member_websites(
    member_id: int,
    db: DbSession,
    actor: CurrentUser,
    include_inactive: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> MemberWebsitesListRead:
    require_admin(actor)
    return member_service.list_member_websites(
        db,
        member_id,
        include_inactive=include_inactive,
        limit=limit,
        offset=offset,
    )


@router.put("/members/{member_id}/websites/{target_id}", status_code=status.HTTP_204_NO_CONTENT)
async def assign_website(
    member_id: int,
    target_id: str,
    db: DbSession,
    actor: CurrentUser,
) -> None:
    require_admin(actor)
    member_service.assign_website(db, actor, member_id, target_id)


@router.delete("/members/{member_id}/websites/{target_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_website_assignment(
    member_id: int,
    target_id: str,
    db: DbSession,
    actor: CurrentUser,
) -> None:
    require_admin(actor)
    member_service.remove_website_assignment(db, actor, member_id, target_id)


@router.get("/member-assignments/websites", response_model=PaginatedMemberWebsitesRead)
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
) -> PaginatedMemberWebsitesRead:
    require_admin(actor)
    return member_service.list_assignment_websites(
        db,
        view=view,
        search=search,
        operator_id=operator_id,
        tag_ids=tag_ids,
        include_inactive=include_inactive,
        limit=limit,
        offset=offset,
    )
