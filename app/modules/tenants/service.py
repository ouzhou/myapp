from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.tenants.models import Tenant
from app.modules.tenants.schemas import TenantCreate


def get_active_tenant(db: Session, tenant_id: UUID) -> Tenant | None:
    return db.scalars(
        select(Tenant).where(
            Tenant.id == tenant_id,
            Tenant.deleted_at.is_(None),
            Tenant.status == Tenant.STATUS_ACTIVE,
        )
    ).first()


def create_tenant(db: Session, payload: TenantCreate, *, tenant_id: UUID | None = None) -> Tenant:
    tenant = Tenant(
        id=tenant_id,
        slug=payload.slug,
        name=payload.name,
        status=payload.status,
    )
    db.add(tenant)
    db.flush()
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
        return existing
    return create_tenant(db, payload, tenant_id=tenant_id)
