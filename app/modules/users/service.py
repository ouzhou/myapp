from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import AppError, BizCode
from app.modules.tenants.models import Tenant
from app.modules.tenants.schemas import TenantSummary
from app.modules.users.models import Membership, User
from app.modules.users.schemas import MeRead, UserCreate, UserProfile

MEMBERSHIP_DENIED = "无权访问该租户"


def require_user(db: Session, user_id: UUID) -> User:
    user = db.scalars(
        select(User).where(
            User.id == user_id,
            User.deleted_at.is_(None),
            User.status == User.STATUS_ACTIVE,
        )
    ).first()
    if user is None:
        raise AppError(BizCode.UNAUTHORIZED, "未认证")
    return user


def get_or_create_user(
    db: Session,
    payload: UserCreate,
    *,
    user_id: UUID | None = None,
) -> User:
    existing = db.scalars(
        select(User).where(User.email == payload.email, User.deleted_at.is_(None))
    ).first()
    if existing is not None:
        return existing
    user = User(
        id=user_id,
        email=payload.email,
        display_name=payload.display_name,
        status=payload.status,
        is_platform_admin=payload.is_platform_admin,
        idp_subject=payload.idp_subject,
    )
    db.add(user)
    db.flush()
    return user


def _active_membership(
    db: Session, user_id: UUID, tenant_id: UUID
) -> Membership | None:
    return db.scalars(
        select(Membership)
        .join(Tenant, Tenant.id == Membership.tenant_id)
        .where(
            Membership.user_id == user_id,
            Membership.tenant_id == tenant_id,
            Membership.status == Membership.STATUS_ACTIVE,
            Tenant.deleted_at.is_(None),
            Tenant.status == Tenant.STATUS_ACTIVE,
        )
    ).first()


def resolve_membership(
    db: Session, user: User, requested_tenant_id: UUID | None
) -> Membership:
    if requested_tenant_id is not None:
        membership = _active_membership(db, user.id, requested_tenant_id)
        if membership is None:
            raise AppError(BizCode.FORBIDDEN, MEMBERSHIP_DENIED)
        return membership

    if user.last_selected_tenant_id is not None:
        membership = _active_membership(db, user.id, user.last_selected_tenant_id)
        if membership is not None:
            return membership

    membership = db.scalars(
        select(Membership)
        .join(Tenant, Tenant.id == Membership.tenant_id)
        .where(
            Membership.user_id == user.id,
            Membership.status == Membership.STATUS_ACTIVE,
            Tenant.deleted_at.is_(None),
            Tenant.status == Tenant.STATUS_ACTIVE,
        )
        .order_by(Membership.created_at.asc(), Membership.id.asc())
    ).first()
    if membership is None:
        raise AppError(BizCode.FORBIDDEN, MEMBERSHIP_DENIED)
    return membership


def get_or_create_membership(
    db: Session,
    *,
    user_id: UUID,
    tenant_id: UUID,
    created_at: datetime | None = None,
) -> Membership:
    existing = db.scalars(
        select(Membership).where(
            Membership.user_id == user_id,
            Membership.tenant_id == tenant_id,
        )
    ).first()
    if existing is not None:
        if existing.status != Membership.STATUS_ACTIVE:
            existing.status = Membership.STATUS_ACTIVE
            db.flush()
        return existing
    membership = Membership(user_id=user_id, tenant_id=tenant_id)
    if created_at is not None:
        membership.created_at = created_at
    db.add(membership)
    db.flush()
    return membership


def _tenant_summaries(db: Session, user_id: UUID) -> list[Tenant]:
    return list(
        db.scalars(
            select(Tenant)
            .join(Membership, Membership.tenant_id == Tenant.id)
            .where(
                Membership.user_id == user_id,
                Membership.status == Membership.STATUS_ACTIVE,
                Tenant.deleted_at.is_(None),
            )
            .order_by(Membership.created_at.asc(), Membership.id.asc())
        ).all()
    )


def get_me(
    db: Session, user_id: UUID, requested_tenant_id: UUID | None
) -> MeRead:
    user = require_user(db, user_id)
    tenants = _tenant_summaries(db, user.id)
    current: Tenant | None
    if requested_tenant_id is not None or tenants:
        membership = resolve_membership(db, user, requested_tenant_id)
        current = db.get(Tenant, membership.tenant_id)
    else:
        current = None
    return MeRead(
        user=UserProfile.model_validate(user),
        tenants=[TenantSummary.model_validate(row) for row in tenants],
        current_tenant=TenantSummary.model_validate(current) if current else None,
    )


def switch_current_tenant(db: Session, user_id: UUID, tenant_id: UUID) -> MeRead:
    user = require_user(db, user_id)
    if _active_membership(db, user.id, tenant_id) is None:
        raise AppError(BizCode.FORBIDDEN, MEMBERSHIP_DENIED)
    user.last_selected_tenant_id = tenant_id
    db.flush()
    return get_me(db, user_id, requested_tenant_id=None)
