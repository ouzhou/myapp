from __future__ import annotations

import sys
from pathlib import Path
from uuid import UUID

from sqlalchemy.orm import Session

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


from app.core.permissions import Perm
from app.db.session import SessionLocal
from app.modules.iam.models import Role
from app.modules.iam.service import ensure_custom_role, ensure_membership_role_by_code
from app.modules.tenants.schemas import TenantCreate
from app.modules.tenants.service import get_or_create_tenant
from app.modules.users.models import User
from app.modules.users.schemas import UserCreate
from app.modules.users.service import get_or_create_membership, get_or_create_user

DEMO_TENANT_ID = UUID("11111111-1111-1111-1111-111111111111")
DEMO_ADMIN_ID = UUID("22222222-2222-2222-2222-222222222222")
DEMO_MEMBER_ID = UUID("33333333-3333-3333-3333-333333333333")
DEMO_PLATFORM_ID = UUID("44444444-4444-4444-4444-444444444444")
DEMO_TENANT_SLUG = "demo"
DEMO_ADMIN_EMAIL = "admin@example.test"
DEMO_MEMBER_EMAIL = "member@example.test"
DEMO_PLATFORM_EMAIL = "platform@example.test"
DEMO_ADMIN_USERNAME = "demo_admin"
DEMO_MEMBER_USERNAME = "demo_member"
DEMO_PLATFORM_USERNAME = "demo_platform"
DEMO_MEMBER_ROLE_CODE = "member"
DEMO_MEMBER_ROLE_NAME = "成员"


def _sync_user(
    db: Session,
    *,
    user_id: UUID,
    email: str,
    display_name: str,
    is_platform_admin: bool,
) -> User:
    user = get_or_create_user(
        db,
        UserCreate(
            email=email,
            display_name=display_name,
            is_platform_admin=is_platform_admin,
        ),
        user_id=user_id,
    )
    user.display_name = display_name
    user.is_platform_admin = is_platform_admin
    db.flush()
    return user


def seed_demo(db: Session) -> None:
    tenant = get_or_create_tenant(
        db,
        TenantCreate(slug=DEMO_TENANT_SLUG, name="Demo"),
        tenant_id=DEMO_TENANT_ID,
    )
    _sync_user(
        db,
        user_id=DEMO_PLATFORM_ID,
        email=DEMO_PLATFORM_EMAIL,
        display_name="平台管理员",
        is_platform_admin=True,
    )
    admin = _sync_user(
        db,
        user_id=DEMO_ADMIN_ID,
        email=DEMO_ADMIN_EMAIL,
        display_name="租户管理员",
        is_platform_admin=False,
    )
    member = _sync_user(
        db,
        user_id=DEMO_MEMBER_ID,
        email=DEMO_MEMBER_EMAIL,
        display_name="普通成员",
        is_platform_admin=False,
    )
    admin_membership = get_or_create_membership(
        db, user_id=admin.id, tenant_id=tenant.id
    )
    member_membership = get_or_create_membership(
        db, user_id=member.id, tenant_id=tenant.id
    )
    ensure_membership_role_by_code(db, admin_membership, Role.CODE_TENANT_ADMIN)
    ensure_custom_role(
        db,
        tenant.id,
        code=DEMO_MEMBER_ROLE_CODE,
        name=DEMO_MEMBER_ROLE_NAME,
        permissions=(Perm.PROJECT_READ,),
    )
    ensure_membership_role_by_code(db, member_membership, DEMO_MEMBER_ROLE_CODE)


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
