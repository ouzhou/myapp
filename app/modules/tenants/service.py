from enum import IntEnum
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import AppError, register_constraint_error
from app.core.response import PageResult, Pagination
from app.modules.tenants.models import Tenant
from app.modules.tenants.schemas import TenantCreate, TenantRead


class TenantCode(IntEnum):
    """tenants 的专属业务码。资源序号 04，编码规则见 core/exceptions.py。"""

    NOT_FOUND = 40404
    SLUG_CONFLICT = 40907


register_constraint_error(
    "uq_tenants_slug_active",
    TenantCode.SLUG_CONFLICT,
    "租户编码已存在",
)


def get_active_tenant(db: Session, tenant_id: UUID) -> Tenant | None:
    return db.scalars(
        select(Tenant).where(
            Tenant.id == tenant_id,
            Tenant.deleted_at.is_(None),
            Tenant.status == Tenant.STATUS_ACTIVE,
        )
    ).first()


def _get_live(db: Session, tenant_id: UUID) -> Tenant:
    tenant = db.scalars(
        select(Tenant).where(Tenant.id == tenant_id, Tenant.deleted_at.is_(None))
    ).first()
    if tenant is None:
        raise AppError(TenantCode.NOT_FOUND, "租户不存在")
    return tenant


def create_tenant(db: Session, payload: TenantCreate, *, tenant_id: UUID | None = None) -> Tenant:
    tenant = Tenant(
        id=tenant_id,
        slug=payload.slug,
        name=payload.name,
        status=Tenant.STATUS_ACTIVE,
    )
    db.add(tenant)
    db.flush()
    from app.modules.iam.service import ensure_system_roles

    ensure_system_roles(db, tenant.id)
    return tenant


def get_or_create_tenant(
    db: Session,
    payload: TenantCreate,
    *,
    tenant_id: UUID | None = None,
) -> Tenant:
    existing = db.scalars(
        select(Tenant).where(Tenant.slug == payload.slug, Tenant.deleted_at.is_(None))
    ).first()
    if existing is not None:
        from app.modules.iam.service import ensure_system_roles

        ensure_system_roles(db, existing.id)
        return existing
    return create_tenant(db, payload, tenant_id=tenant_id)


def set_tenant_status(db: Session, tenant_id: UUID, status: str) -> Tenant:
    tenant = _get_live(db, tenant_id)
    tenant.status = status
    db.flush()
    return tenant


def list_tenants(db: Session, pagination: Pagination) -> PageResult[TenantRead]:
    conditions = [Tenant.deleted_at.is_(None)]
    total = db.scalar(select(func.count()).select_from(Tenant).where(*conditions)) or 0
    rows = db.scalars(
        select(Tenant)
        .where(*conditions)
        .order_by(Tenant.created_at.asc(), Tenant.id.asc())
        .offset((pagination.page - 1) * pagination.page_size)
        .limit(pagination.page_size)
    )
    return PageResult(
        items=[TenantRead.model_validate(row) for row in rows],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )
