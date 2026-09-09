from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.permissions import Perm
from app.core.context import CurrentUser
from app.core.exceptions import BizCode
from app.core.response import PageResult, Pagination
from app.modules.projects import service as project_service
from app.modules.projects.schemas import ProjectQuery, ProjectRead
from tests.conftest import auth_headers, ensure_identity


def test_missing_identity_headers_is_401(client: TestClient) -> None:
    response = client.get("/api/v1/projects/")
    assert response.status_code == 401
    assert response.json()["code"] == BizCode.UNAUTHORIZED
    assert response.json()["message"] == "未认证"


def test_unknown_user_header_is_401(client: TestClient) -> None:
    response = client.get(
        "/api/v1/projects/",
        headers={"X-User-Id": str(uuid4()), "X-Tenant-Id": str(uuid4())},
    )
    assert response.status_code == 401
    assert response.json()["code"] == BizCode.UNAUTHORIZED


def test_prod_rejects_header_auth(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "environment", "prod")
    response = client.get("/api/v1/projects/", headers=auth_headers(db_session))
    assert response.status_code == 401
    assert response.json()["code"] == BizCode.UNAUTHORIZED


def test_service_receives_current_user_from_headers(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: list[CurrentUser] = []
    original = project_service.list_projects

    def spy(
        db: Session,
        user: CurrentUser,
        query: ProjectQuery,
        pagination: Pagination,
    ) -> PageResult[ProjectRead]:
        captured.append(user)
        return original(db, user, query, pagination)

    monkeypatch.setattr(project_service, "list_projects", spy)

    user_id = uuid4()
    tenant_id = uuid4()
    _uid, _tid, membership_id = ensure_identity(
        db_session,
        user_id=user_id,
        tenant_id=tenant_id,
        is_platform_admin=True,
    )
    response = client.get(
        "/api/v1/projects/",
        headers={
            "X-User-Id": str(user_id),
            "X-Tenant-Id": str(tenant_id),
        },
    )
    assert response.status_code == 200
    assert len(captured) == 1
    assert captured[0].user_id == user_id
    assert captured[0].tenant_id == tenant_id
    assert captured[0].membership_id == membership_id
    assert set(captured[0].permissions) == {perm.value for perm in Perm}
    assert captured[0].is_platform_admin is True


def test_missing_tenant_header_falls_back_to_membership(
    client: TestClient, db_session: Session
) -> None:
    headers = auth_headers(db_session, include_tenant=False)
    response = client.get("/api/v1/projects/", headers=headers)
    assert response.status_code == 200
