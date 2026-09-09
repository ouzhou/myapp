from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import BizCode
from app.core.permissions import Perm
from app.modules.iam.models import MembershipRole, Role
from app.modules.tenants.models import Tenant
from app.modules.users.models import Membership, User
from scripts.seed import (
    DEMO_ADMIN_EMAIL,
    DEMO_MEMBER_EMAIL,
    DEMO_PLATFORM_EMAIL,
    DEMO_TENANT_SLUG,
    seed_demo,
)
from tests.conftest import auth_headers, ensure_identity


def test_me_lists_all_tenants_and_falls_back_to_earliest(
    client: TestClient, db_session: Session
) -> None:
    user_id = uuid4()
    tenant_a = uuid4()
    tenant_b = uuid4()
    ensure_identity(
        db_session,
        user_id=user_id,
        tenant_id=tenant_a,
        membership_created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    ensure_identity(
        db_session,
        user_id=user_id,
        tenant_id=tenant_b,
        membership_created_at=datetime(2026, 1, 2, tzinfo=UTC),
    )

    response = client.get("/api/v1/me", headers={"X-User-Id": str(user_id)})
    assert response.status_code == 200
    body = response.json()["data"]
    tenant_ids = [row["id"] for row in body["tenants"]]
    assert tenant_ids == [str(tenant_a), str(tenant_b)]
    assert body["current_tenant"]["id"] == str(tenant_a)
    assert "idp_subject" not in body["user"]
    assert "password" not in str(body).lower()
    assert set(body["permissions"]) == {perm.value for perm in Perm}


def test_me_permissions_follow_the_current_tenant_role(
    client: TestClient, db_session: Session
) -> None:
    tenant_id = uuid4()
    headers = auth_headers(db_session, tenant_id=tenant_id)
    admin_me = client.get("/api/v1/me", headers=headers)
    assert admin_me.status_code == 200
    assert set(admin_me.json()["data"]["permissions"]) == {perm.value for perm in Perm}

    reader_id = uuid4()
    ensure_identity(
        db_session, user_id=reader_id, tenant_id=tenant_id, role_code="member"
    )
    reader_me = client.get(
        "/api/v1/me",
        headers={"X-User-Id": str(reader_id), "X-Tenant-Id": str(tenant_id)},
    )
    assert reader_me.status_code == 200
    assert reader_me.json()["data"]["permissions"] == [Perm.PROJECT_READ.value]


def test_switch_current_tenant_then_fallback_uses_it(
    client: TestClient, db_session: Session
) -> None:
    user_id = uuid4()
    tenant_a = uuid4()
    tenant_b = uuid4()
    ensure_identity(
        db_session,
        user_id=user_id,
        tenant_id=tenant_a,
        membership_created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    ensure_identity(
        db_session,
        user_id=user_id,
        tenant_id=tenant_b,
        membership_created_at=datetime(2026, 1, 2, tzinfo=UTC),
    )

    switched = client.put(
        "/api/v1/me/current-tenant",
        headers={"X-User-Id": str(user_id)},
        json={"tenant_id": str(tenant_b)},
    )
    assert switched.status_code == 200
    assert switched.json()["data"]["current_tenant"]["id"] == str(tenant_b)

    again = client.get("/api/v1/me", headers={"X-User-Id": str(user_id)})
    assert again.status_code == 200
    assert again.json()["data"]["current_tenant"]["id"] == str(tenant_b)

    listed = client.get("/api/v1/projects/", headers={"X-User-Id": str(user_id)})
    assert listed.status_code == 200


def test_switch_to_foreign_tenant_is_403(
    client: TestClient, db_session: Session
) -> None:
    headers = auth_headers(db_session)
    foreign = uuid4()
    ensure_identity(db_session, tenant_id=foreign)
    response = client.put(
        "/api/v1/me/current-tenant",
        headers=headers,
        json={"tenant_id": str(foreign)},
    )
    assert response.status_code == 403
    assert response.json()["code"] == BizCode.FORBIDDEN
    assert response.json()["message"] == "无权访问该租户"


def test_seed_is_idempotent(db_session: Session) -> None:
    seed_demo(db_session)
    seed_demo(db_session)
    assert db_session.scalar(select(func.count()).select_from(Tenant)) == 1
    assert db_session.scalar(select(func.count()).select_from(User)) == 3
    assert db_session.scalar(select(func.count()).select_from(Membership)) == 2
    assert db_session.scalar(select(func.count()).select_from(Role)) == 2
    assert db_session.scalar(select(func.count()).select_from(MembershipRole)) == 2
    emails = set(db_session.scalars(select(User.email)))
    assert emails == {DEMO_PLATFORM_EMAIL, DEMO_ADMIN_EMAIL, DEMO_MEMBER_EMAIL}
    assert db_session.scalars(select(Tenant.slug)).first() == DEMO_TENANT_SLUG


def test_user_model_has_no_password_fields() -> None:
    names = {column.name for column in User.__table__.columns}
    assert not any("password" in name for name in names)
