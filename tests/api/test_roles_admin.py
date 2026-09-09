from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import BizCode
from app.core.permissions import Perm
from app.modules.iam.models import MembershipRole, Role
from app.modules.iam.service import IamCode
from tests.conftest import auth_headers, ensure_identity


def _role(db: Session, tenant_id, code: str) -> Role:
    return db.scalars(
        select(Role).where(Role.tenant_id == tenant_id, Role.code == code)
    ).one()


def test_permissions_catalog_comes_from_enum(auth_client: TestClient) -> None:
    response = auth_client.get("/api/v1/permissions")
    assert response.status_code == 200
    codes = [row["code"] for row in response.json()["data"]]
    assert codes == [perm.value for perm in Perm]


def test_system_roles_are_seeded_and_protected(
    client: TestClient, db_session: Session
) -> None:
    headers = auth_headers(db_session)
    listed = client.get("/api/v1/roles", headers=headers)
    assert listed.status_code == 200
    codes = {row["code"] for row in listed.json()["data"]["items"]}
    assert codes == {"tenant_admin"}
    admin = next(
        row for row in listed.json()["data"]["items"] if row["code"] == "tenant_admin"
    )
    assert admin["is_system"] is True
    assert set(admin["permissions"]) == {perm.value for perm in Perm}

    deleted = client.delete(f"/api/v1/roles/{admin['id']}", headers=headers)
    assert deleted.status_code == 409
    assert deleted.json()["code"] == IamCode.SYSTEM_ROLE_PROTECTED

    renamed = client.patch(
        f"/api/v1/roles/{admin['id']}",
        json={"code": "root"},
        headers=headers,
    )
    assert renamed.status_code == 409
    assert renamed.json()["code"] == IamCode.SYSTEM_ROLE_PROTECTED

    locked = client.put(
        f"/api/v1/roles/{admin['id']}/permissions",
        json={"permissions": [Perm.PROJECT_READ.value]},
        headers=headers,
    )
    assert locked.status_code == 409
    assert locked.json()["code"] == IamCode.SYSTEM_PERMS_LOCKED


def test_custom_role_crud(auth_client: TestClient) -> None:
    created = auth_client.post(
        "/api/v1/roles",
        json={"code": "reviewer", "name": "审核", "permissions": [Perm.PROJECT_READ.value]},
    )
    assert created.status_code == 201
    role_id = created.json()["data"]["id"]
    assert created.json()["data"]["is_system"] is False

    conflicted = auth_client.post(
        "/api/v1/roles",
        json={"code": "reviewer", "name": "重复"},
    )
    assert conflicted.status_code == 409
    assert conflicted.json()["code"] == IamCode.ROLE_CODE_CONFLICT

    updated = auth_client.patch(
        f"/api/v1/roles/{role_id}",
        json={"name": "审核员"},
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["name"] == "审核员"

    deleted = auth_client.delete(f"/api/v1/roles/{role_id}")
    assert deleted.status_code == 204
    listed = auth_client.get("/api/v1/roles")
    assert role_id not in [row["id"] for row in listed.json()["data"]["items"]]


def test_foreign_role_cannot_be_granted_to_member(
    client: TestClient, db_session: Session
) -> None:
    tenant_a = uuid4()
    tenant_b = uuid4()
    headers_a = auth_headers(db_session, tenant_id=tenant_a)
    _user_id, _tid, membership_id = ensure_identity(
        db_session, tenant_id=tenant_a, role_code="member"
    )
    auth_headers(db_session, tenant_id=tenant_b)
    foreign_role = _role(db_session, tenant_b, Role.CODE_TENANT_ADMIN)

    response = client.put(
        f"/api/v1/members/{membership_id}/roles",
        json={"role_ids": [str(foreign_role.id)]},
        headers=headers_a,
    )
    assert response.status_code == 422
    assert response.json()["code"] == BizCode.VALIDATION_ERROR
    assert response.json()["message"] == "角色不属于当前租户"


def test_composite_fk_blocks_cross_tenant_grant(db_session: Session) -> None:
    _uid_a, tenant_a, membership_a = ensure_identity(db_session)
    _uid_b, tenant_b, _membership_b = ensure_identity(db_session)
    role_b = _role(db_session, tenant_b, Role.CODE_TENANT_ADMIN)
    nested = db_session.begin_nested()
    try:
        db_session.add(
            MembershipRole(
                membership_id=membership_a,
                role_id=role_b.id,
                tenant_id=tenant_a,
            )
        )
        db_session.flush()
        raise AssertionError("cross-tenant grant should be rejected")
    except IntegrityError:
        nested.rollback()


def test_add_and_remove_member(auth_client: TestClient) -> None:
    created = auth_client.post(
        "/api/v1/members",
        json={
            "email": f"new-{uuid4().hex}@example.test",
            "display_name": "新成员",
            "role_ids": [],
        },
    )
    assert created.status_code == 201
    membership_id = created.json()["data"]["id"]
    listed = auth_client.get("/api/v1/members")
    assert membership_id in [row["id"] for row in listed.json()["data"]["items"]]

    removed = auth_client.delete(f"/api/v1/members/{membership_id}")
    assert removed.status_code == 204
    listed_again = auth_client.get("/api/v1/members")
    assert membership_id not in [
        row["id"] for row in listed_again.json()["data"]["items"]
    ]
