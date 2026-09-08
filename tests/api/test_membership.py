from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import BizCode
from app.modules.users.models import Membership
from tests.conftest import auth_headers, ensure_identity


def test_foreign_tenant_header_is_403_same_as_unknown(
    client: TestClient, db_session: Session
) -> None:
    headers = auth_headers(db_session)
    foreign_tenant = uuid4()
    ensure_identity(db_session, tenant_id=foreign_tenant)

    not_member = client.get(
        "/api/v1/projects/",
        headers={
            "X-User-Id": headers["X-User-Id"],
            "X-Tenant-Id": str(foreign_tenant),
        },
    )
    unknown = client.get(
        "/api/v1/projects/",
        headers={
            "X-User-Id": headers["X-User-Id"],
            "X-Tenant-Id": str(uuid4()),
        },
    )
    assert not_member.status_code == 403
    assert unknown.status_code == 403
    assert not_member.json()["code"] == BizCode.FORBIDDEN
    assert not_member.json()["message"] == unknown.json()["message"] == "无权访问该租户"


def test_removing_membership_hides_projects(
    client: TestClient, db_session: Session
) -> None:
    headers = auth_headers(db_session)
    created = client.post(
        "/api/v1/projects/",
        json={"name": f"project-{uuid4()}"},
        headers=headers,
    )
    assert created.status_code == 201
    project_id = created.json()["data"]["id"]

    membership = db_session.scalars(
        select(Membership).where(
            Membership.user_id == UUID(headers["X-User-Id"]),
            Membership.tenant_id == UUID(headers["X-Tenant-Id"]),
        )
    ).one()
    db_session.delete(membership)
    db_session.flush()

    hidden = client.get(f"/api/v1/projects/{project_id}", headers=headers)
    assert hidden.status_code == 403
    assert hidden.json()["message"] == "无权访问该租户"
