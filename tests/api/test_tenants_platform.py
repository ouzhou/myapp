from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import BizCode
from app.modules.iam.models import Role
from app.modules.tenants.service import TenantCode
from app.modules.users.schemas import UserCreate
from app.modules.users.service import get_or_create_user
from scripts.seed import DEMO_PLATFORM_ID, DEMO_TENANT_SLUG, seed_demo
from tests.conftest import auth_headers, ensure_identity


def test_platform_admin_lists_tenants_without_membership(
    client: TestClient, db_session: Session
) -> None:
    seed_demo(db_session)
    response = client.get(
        "/api/v1/tenants", headers={"X-User-Id": str(DEMO_PLATFORM_ID)}
    )
    assert response.status_code == 200
    slugs = [row["slug"] for row in response.json()["data"]["items"]]
    assert DEMO_TENANT_SLUG in slugs


def test_tenant_admin_cannot_list_tenants(
    client: TestClient, db_session: Session
) -> None:
    headers = auth_headers(db_session)
    response = client.get("/api/v1/tenants", headers=headers)
    assert response.status_code == 403
    assert response.json()["code"] == BizCode.FORBIDDEN


def test_platform_admin_me_has_no_tenant(
    client: TestClient, db_session: Session
) -> None:
    user = get_or_create_user(
        db_session,
        UserCreate(
            email=f"ops-{uuid4().hex[:8]}@example.test",
            display_name="平台",
            is_platform_admin=True,
        ),
    )
    response = client.get("/api/v1/me", headers={"X-User-Id": str(user.id)})
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["user"]["is_platform_admin"] is True
    assert body["tenants"] == []
    assert body["current_tenant"] is None
    assert body["permissions"] == []


def test_platform_admin_cannot_read_tenant_projects_without_membership(
    client: TestClient, db_session: Session
) -> None:
    tenant_id = uuid4()
    ensure_identity(db_session, tenant_id=tenant_id)
    platform = get_or_create_user(
        db_session,
        UserCreate(
            email=f"ops-{uuid4().hex[:8]}@example.test",
            display_name="平台",
            is_platform_admin=True,
        ),
    )
    response = client.get(
        "/api/v1/projects/",
        headers={"X-User-Id": str(platform.id), "X-Tenant-Id": str(tenant_id)},
    )
    assert response.status_code == 403
    assert response.json()["message"] == "无权访问该租户"


def _platform_headers(db_session: Session) -> dict[str, str]:
    user = get_or_create_user(
        db_session,
        UserCreate(
            email=f"ops-{uuid4().hex[:8]}@example.test",
            display_name="平台",
            is_platform_admin=True,
        ),
    )
    return {"X-User-Id": str(user.id)}


def test_platform_admin_creates_tenant_with_system_role(
    client: TestClient, db_session: Session
) -> None:
    headers = _platform_headers(db_session)
    slug = f"acme-{uuid4().hex[:8]}"
    response = client.post(
        "/api/v1/tenants",
        headers=headers,
        json={"slug": slug, "name": "Acme"},
    )
    assert response.status_code == 201
    body = response.json()["data"]
    assert body["slug"] == slug
    assert body["name"] == "Acme"
    assert body["status"] == "active"

    codes = set(
        db_session.scalars(select(Role.code).where(Role.tenant_id == body["id"]))
    )
    assert codes == {"tenant_admin"}


def test_create_tenant_rejects_duplicate_slug(
    client: TestClient, db_session: Session
) -> None:
    headers = _platform_headers(db_session)
    payload = {"slug": f"dup-{uuid4().hex[:8]}", "name": "One"}
    first = client.post("/api/v1/tenants", headers=headers, json=payload)
    assert first.status_code == 201
    second = client.post("/api/v1/tenants", headers=headers, json=payload)
    assert second.status_code == 409
    assert second.json()["code"] == TenantCode.SLUG_CONFLICT


def test_tenant_admin_cannot_create_or_patch_tenants(
    client: TestClient, db_session: Session
) -> None:
    headers = auth_headers(db_session)
    created = client.post(
        "/api/v1/tenants",
        headers=headers,
        json={"slug": "nope", "name": "Nope"},
    )
    assert created.status_code == 403
    patched = client.patch(
        f"/api/v1/tenants/{uuid4()}",
        headers=headers,
        json={"status": "disabled"},
    )
    assert patched.status_code == 403


def test_platform_admin_disables_and_enables_tenant(
    client: TestClient, db_session: Session
) -> None:
    tenant_id = uuid4()
    member_headers = auth_headers(db_session, tenant_id=tenant_id)
    platform = _platform_headers(db_session)

    disabled = client.patch(
        f"/api/v1/tenants/{tenant_id}",
        headers=platform,
        json={"status": "disabled"},
    )
    assert disabled.status_code == 200
    assert disabled.json()["data"]["status"] == "disabled"

    blocked = client.get("/api/v1/projects/", headers=member_headers)
    assert blocked.status_code == 403
    assert blocked.json()["message"] == "无权访问该租户"

    me = client.get("/api/v1/me", headers={"X-User-Id": member_headers["X-User-Id"]})
    assert me.status_code == 200
    assert me.json()["data"]["tenants"] == []

    listed = client.get("/api/v1/tenants", headers=platform)
    match = next(
        row for row in listed.json()["data"]["items"] if row["id"] == str(tenant_id)
    )
    assert match["status"] == "disabled"

    enabled = client.patch(
        f"/api/v1/tenants/{tenant_id}",
        headers=platform,
        json={"status": "active"},
    )
    assert enabled.status_code == 200
    assert enabled.json()["data"]["status"] == "active"

    restored = client.get("/api/v1/projects/", headers=member_headers)
    assert restored.status_code == 200

    missing = client.patch(
        f"/api/v1/tenants/{uuid4()}",
        headers=platform,
        json={"status": "disabled"},
    )
    assert missing.status_code == 404
    assert missing.json()["code"] == TenantCode.NOT_FOUND
