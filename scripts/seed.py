from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.modules.tenants.schemas import TenantCreate
from app.modules.tenants.service import get_or_create_tenant
from app.modules.users.schemas import UserCreate
from app.modules.iam.models import Role
from app.modules.iam.service import ensure_membership_role_by_code
from app.modules.users.service import get_or_create_membership, get_or_create_user

DEMO_TENANT_ID = UUID("11111111-1111-1111-1111-111111111111")
DEMO_ADMIN_ID = UUID("22222222-2222-2222-2222-222222222222")
DEMO_MEMBER_ID = UUID("33333333-3333-3333-3333-333333333333")
DEMO_TENANT_SLUG = "demo"
DEMO_ADMIN_EMAIL = "admin@example.test"
DEMO_MEMBER_EMAIL = "member@example.test"


def seed_demo(db: Session) -> None:
    tenant = get_or_create_tenant(
        db,
        TenantCreate(slug=DEMO_TENANT_SLUG, name="Demo"),
        tenant_id=DEMO_TENANT_ID,
    )
    admin = get_or_create_user(
        db,
        UserCreate(
            email=DEMO_ADMIN_EMAIL,
            display_name="平台管理员",
            is_platform_admin=True,
        ),
        user_id=DEMO_ADMIN_ID,
    )
    member = get_or_create_user(
        db,
        UserCreate(
            email=DEMO_MEMBER_EMAIL,
            display_name="普通成员",
        ),
        user_id=DEMO_MEMBER_ID,
    )
    admin_membership = get_or_create_membership(
        db, user_id=admin.id, tenant_id=tenant.id
    )
    member_membership = get_or_create_membership(
        db, user_id=member.id, tenant_id=tenant.id
    )
    ensure_membership_role_by_code(db, admin_membership, Role.CODE_OWNER)
    ensure_membership_role_by_code(db, member_membership, Role.CODE_MEMBER)


def main() -> None:
    session = SessionLocal()
    try:
        seed_demo(session)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
