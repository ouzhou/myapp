from typing import Any
from uuid import UUID

from fastapi import APIRouter, status

from app.core.response import Envelope, ErrorEnvelope, PageResult, PaginationParams, ok
from app.deps import DbSession, PlatformAdminDep
from app.modules.tenants import service as tenant_service
from app.modules.tenants.schemas import TenantCreate, TenantRead, TenantStatusUpdate

UNAUTHORIZED: dict[int | str, dict[str, Any]] = {401: {"model": ErrorEnvelope}}
FORBIDDEN: dict[int | str, dict[str, Any]] = {403: {"model": ErrorEnvelope}}
NOT_FOUND: dict[int | str, dict[str, Any]] = {404: {"model": ErrorEnvelope}}
CONFLICT: dict[int | str, dict[str, Any]] = {409: {"model": ErrorEnvelope}}

router = APIRouter(tags=["tenants"], responses=UNAUTHORIZED | FORBIDDEN)


@router.get("/tenants")
def list_tenants(
    db: DbSession,
    _admin: PlatformAdminDep,
    pagination: PaginationParams,
) -> Envelope[PageResult[TenantRead]]:
    return ok(tenant_service.list_tenants(db, pagination))


@router.post("/tenants", status_code=status.HTTP_201_CREATED, responses=CONFLICT)
def create_tenant(
    payload: TenantCreate,
    db: DbSession,
    _admin: PlatformAdminDep,
) -> Envelope[TenantRead]:
    return ok(TenantRead.model_validate(tenant_service.create_tenant(db, payload)))


@router.patch("/tenants/{tenant_id}", responses=NOT_FOUND)
def update_tenant_status(
    tenant_id: UUID,
    payload: TenantStatusUpdate,
    db: DbSession,
    _admin: PlatformAdminDep,
) -> Envelope[TenantRead]:
    return ok(
        TenantRead.model_validate(
            tenant_service.set_tenant_status(db, tenant_id, payload.status)
        )
    )
