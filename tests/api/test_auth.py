from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.context import CurrentUser
from app.core.exceptions import BizCode
from app.core.response import PageResult, Pagination
from app.modules.projects import service as project_service
from app.modules.projects.schemas import ProjectQuery, ProjectRead


def test_missing_identity_headers_is_401(client: TestClient) -> None:
    response = client.get("/api/v1/projects/")
    assert response.status_code == 401
    assert response.json()["code"] == BizCode.UNAUTHORIZED
    assert response.json()["message"] == "未认证"


def test_prod_rejects_header_auth(
    auth_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "environment", "prod")
    response = auth_client.get("/api/v1/projects/")
    assert response.status_code == 401
    assert response.json()["code"] == BizCode.UNAUTHORIZED


def test_service_receives_current_user_from_headers(
    auth_client: TestClient, monkeypatch: pytest.MonkeyPatch
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
    response = auth_client.get(
        "/api/v1/projects/",
        headers={
            "X-User-Id": str(user_id),
            "X-Tenant-Id": str(tenant_id),
            "X-Roles": "annotator, reviewer",
        },
    )
    assert response.status_code == 200
    assert len(captured) == 1
    assert captured[0].user_id == user_id
    assert captured[0].tenant_id == tenant_id
    assert captured[0].roles == ["annotator", "reviewer"]
