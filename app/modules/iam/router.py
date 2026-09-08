from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.core.context import CurrentUser
from app.core.permissions import Perm, require_perm
from app.core.response import Envelope, ErrorEnvelope, PageResult, PaginationParams, ok
from app.deps import DbSession
from app.modules.iam import service as iam_service
from app.modules.iam.schemas import (
    MemberCreate,
    MemberRead,
    MemberRolesUpdate,
    PermissionRead,
    RoleCreate,
    RolePermissionsUpdate,
    RoleRead,
    RoleUpdate,
)

UNAUTHORIZED: dict[int | str, dict[str, Any]] = {401: {"model": ErrorEnvelope}}
FORBIDDEN: dict[int | str, dict[str, Any]] = {403: {"model": ErrorEnvelope}}
NOT_FOUND: dict[int | str, dict[str, Any]] = {404: {"model": ErrorEnvelope}}
CONFLICT: dict[int | str, dict[str, Any]] = {409: {"model": ErrorEnvelope}}

RoleReader = Annotated[CurrentUser, Depends(require_perm(Perm.ROLE_READ))]
RoleWriter = Annotated[CurrentUser, Depends(require_perm(Perm.ROLE_WRITE))]
MemberReader = Annotated[CurrentUser, Depends(require_perm(Perm.MEMBER_READ))]
MemberWriter = Annotated[CurrentUser, Depends(require_perm(Perm.MEMBER_WRITE))]

router = APIRouter(tags=["iam"], responses=UNAUTHORIZED | FORBIDDEN)


@router.get("/permissions")
def list_permissions(_user: RoleReader) -> Envelope[list[PermissionRead]]:
    return ok(iam_service.list_permission_catalog())


@router.get("/roles")
def list_roles(
    db: DbSession,
    user: RoleReader,
    pagination: PaginationParams,
) -> Envelope[PageResult[RoleRead]]:
    return ok(iam_service.list_roles(db, user, pagination))


@router.post("/roles", status_code=status.HTTP_201_CREATED, responses=CONFLICT)
def create_role(
    payload: RoleCreate,
    db: DbSession,
    user: RoleWriter,
) -> Envelope[RoleRead]:
    return ok(iam_service.create_role(db, user, payload))


@router.patch("/roles/{role_id}", responses=NOT_FOUND | CONFLICT)
def update_role(
    role_id: UUID,
    payload: RoleUpdate,
    db: DbSession,
    user: RoleWriter,
) -> Envelope[RoleRead]:
    return ok(iam_service.update_role(db, user, role_id, payload))


@router.delete(
    "/roles/{role_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=NOT_FOUND | CONFLICT,
)
def delete_role(role_id: UUID, db: DbSession, user: RoleWriter) -> None:
    iam_service.delete_role(db, user, role_id)


@router.put("/roles/{role_id}/permissions", responses=NOT_FOUND | CONFLICT)
def put_role_permissions(
    role_id: UUID,
    payload: RolePermissionsUpdate,
    db: DbSession,
    user: RoleWriter,
) -> Envelope[RoleRead]:
    return ok(
        iam_service.replace_role_permissions(db, user, role_id, payload.permissions)
    )


@router.get("/members")
def list_members(
    db: DbSession,
    user: MemberReader,
    pagination: PaginationParams,
) -> Envelope[PageResult[MemberRead]]:
    return ok(iam_service.list_members(db, user, pagination))


@router.post("/members", status_code=status.HTTP_201_CREATED, responses=CONFLICT)
def create_member(
    payload: MemberCreate,
    db: DbSession,
    user: MemberWriter,
) -> Envelope[MemberRead]:
    return ok(iam_service.create_member(db, user, payload))


@router.delete(
    "/members/{membership_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=NOT_FOUND | CONFLICT,
)
def delete_member(membership_id: UUID, db: DbSession, user: MemberWriter) -> None:
    iam_service.delete_member(db, user, membership_id)


@router.put("/members/{membership_id}/roles", responses=NOT_FOUND | CONFLICT)
def put_member_roles(
    membership_id: UUID,
    payload: MemberRolesUpdate,
    db: DbSession,
    user: MemberWriter,
) -> Envelope[MemberRead]:
    return ok(
        iam_service.replace_member_roles(db, user, membership_id, payload.role_ids)
    )
