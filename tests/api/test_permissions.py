from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import BizCode
from app.core.permissions import Perm
from app.modules.audit.models import AuditLog
from app.modules.iam.models import RolePermission
from app.modules.iam.service import IamCode, RESOURCE_ROLE
from tests.conftest import auth_headers, ensure_identity


def test_write_requires_permission_and_identity(
    client: TestClient, db_session: Session
) -> None:
    tenant_id = uuid4()
    owner = auth_headers(db_session, tenant_id=tenant_id)
    reader_id = uuid4()
    ensure_identity(
        db_session, user_id=reader_id, tenant_id=tenant_id, role_code="member"
    )
    reader = {"X-User-Id": str(reader_id), "X-Tenant-Id": str(tenant_id)}
    name = f"project-{uuid4()}"

    created = client.post("/api/v1/projects/", json={"name": name}, headers=owner)
    assert created.status_code == 201
    project_id = created.json()["data"]["id"]

    forbidden = client.patch(
        f"/api/v1/projects/{project_id}",
        json={"name": f"renamed-{uuid4()}"},
        headers=reader,
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == BizCode.FORBIDDEN
    assert forbidden.json()["message"] == "没有权限"

    allowed = client.patch(
        f"/api/v1/projects/{project_id}",
        json={"name": f"renamed-{uuid4()}"},
        headers=owner,
    )
    assert allowed.status_code == 200

    unauthenticated = client.patch(
        f"/api/v1/projects/{project_id}",
        json={"name": f"anon-{uuid4()}"},
    )
    assert unauthenticated.status_code == 401
    assert unauthenticated.json()["code"] == BizCode.UNAUTHORIZED


def test_reader_can_list_but_cannot_create(
    client: TestClient, db_session: Session
) -> None:
    reader = auth_headers(db_session, role_code="member")
    listed = client.get("/api/v1/projects/", headers=reader)
    assert listed.status_code == 200
    created = client.post(
        "/api/v1/projects/",
        json={"name": f"project-{uuid4()}"},
        headers=reader,
    )
    assert created.status_code == 403


def test_custom_role_takes_effect_on_next_request_and_stays_in_tenant(
    client: TestClient, db_session: Session
) -> None:
    tenant_a = uuid4()
    tenant_b = uuid4()
    writer_id = uuid4()
    owner_a = auth_headers(db_session, tenant_id=tenant_a)
    ensure_identity(
        db_session, user_id=writer_id, tenant_id=tenant_a, role_code="member"
    )
    ensure_identity(
        db_session, user_id=writer_id, tenant_id=tenant_b, role_code="member"
    )
    writer_a = {
        "X-User-Id": str(writer_id),
        "X-Tenant-Id": str(tenant_a),
    }
    writer_b = {
        "X-User-Id": str(writer_id),
        "X-Tenant-Id": str(tenant_b),
    }

    blocked = client.post(
        "/api/v1/projects/",
        json={"name": f"project-{uuid4()}"},
        headers=writer_a,
    )
    assert blocked.status_code == 403

    created_role = client.post(
        "/api/v1/roles",
        json={
            "code": "writer",
            "name": "写作者",
            "permissions": [Perm.PROJECT_READ.value, Perm.PROJECT_WRITE.value],
        },
        headers=owner_a,
    )
    assert created_role.status_code == 201
    role_id = created_role.json()["data"]["id"]
    membership_id = ensure_identity(
        db_session, user_id=writer_id, tenant_id=tenant_a, role_code=None
    )[2]
    granted = client.put(
        f"/api/v1/members/{membership_id}/roles",
        json={"role_ids": [role_id]},
        headers=owner_a,
    )
    assert granted.status_code == 200

    now_allowed = client.post(
        "/api/v1/projects/",
        json={"name": f"project-{uuid4()}"},
        headers=writer_a,
    )
    assert now_allowed.status_code == 201

    other_tenant = client.post(
        "/api/v1/projects/",
        json={"name": f"project-{uuid4()}"},
        headers=writer_b,
    )
    assert other_tenant.status_code == 403


def test_unknown_permission_point_is_422(
    auth_client: TestClient,
) -> None:
    created = auth_client.post(
        "/api/v1/roles",
        json={"code": "reviewer", "name": "审核", "permissions": []},
    )
    assert created.status_code == 201
    role_id = created.json()["data"]["id"]
    response = auth_client.put(
        f"/api/v1/roles/{role_id}/permissions",
        json={"permissions": ["porject:write"]},
    )
    assert response.status_code == 422
    assert response.json()["code"] == BizCode.VALIDATION_ERROR


def test_revoking_last_tenant_admin_is_409(
    client: TestClient, db_session: Session
) -> None:
    user_id, tenant_id, membership_id = ensure_identity(db_session)
    response = client.put(
        f"/api/v1/members/{membership_id}/roles",
        json={"role_ids": []},
        headers={"X-User-Id": str(user_id), "X-Tenant-Id": str(tenant_id)},
    )
    assert response.status_code == 409
    assert response.json()["code"] == IamCode.LAST_TENANT_ADMIN


def test_permission_change_writes_audit_row(
    auth_client: TestClient, db_session: Session
) -> None:
    created = auth_client.post(
        "/api/v1/roles",
        json={
            "code": "reviewer",
            "name": "审核",
            "permissions": [Perm.PROJECT_READ.value, Perm.PROJECT_WRITE.value],
        },
    )
    assert created.status_code == 201
    role_id = created.json()["data"]["id"]
    response = auth_client.put(
        f"/api/v1/roles/{role_id}/permissions",
        json={"permissions": [Perm.PROJECT_READ.value]},
        headers={"X-Request-ID": "perm-audit-1"},
    )
    assert response.status_code == 200
    rows = db_session.scalars(
        select(AuditLog).where(
            AuditLog.resource_id == UUID(role_id),
            AuditLog.resource_type == RESOURCE_ROLE,
            AuditLog.action == "update",
        )
    ).all()
    assert len(rows) == 1
    assert rows[0].request_id == "perm-audit-1"
    assert rows[0].after is not None
    assert rows[0].after["permissions"] == [Perm.PROJECT_READ.value]


def test_audit_failure_rolls_back_permission_change(db_session: Session) -> None:
    from app.core.context import CurrentUser
    from app.core.permissions import Perm as PermEnum
    from app.modules.iam import service as iam_service

    user_id, tenant_id, membership_id = ensure_identity(db_session)
    user = CurrentUser(
        user_id=user_id,
        tenant_id=tenant_id,
        membership_id=membership_id,
        permissions=[perm.value for perm in PermEnum],
    )
    role = iam_service.ensure_custom_role(
        db_session,
        tenant_id,
        code="reviewer",
        name="审核",
        permissions=[PermEnum.PROJECT_READ, PermEnum.PROJECT_WRITE],
    )
    original = set(
        db_session.scalars(
            select(RolePermission.permission).where(RolePermission.role_id == role.id)
        )
    )

    nested = db_session.begin_nested()
    try:
        iam_service.replace_role_permissions(
            db_session, user, role.id, [PermEnum.PROJECT_READ]
        )
        raise RuntimeError("simulated failure after audit")
    except RuntimeError:
        nested.rollback()

    db_session.expire_all()
    remaining = set(
        db_session.scalars(
            select(RolePermission.permission).where(RolePermission.role_id == role.id)
        )
    )
    assert remaining == original
