from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import BizCode
from app.modules.projects import service as project_service
from app.modules.projects.service import ProjectCode

_ERROR_ENVELOPE_KEYS = {"code", "message", "data", "details", "request_id"}
_SUCCESS_ENVELOPE_KEYS = {"code", "message", "data"}


def _assert_error_envelope(body: object) -> dict[str, object]:
    assert isinstance(body, dict)
    assert set(body) == _ERROR_ENVELOPE_KEYS
    assert body["data"] is None
    return body


def test_success_envelope_carries_no_error_fields(auth_client: TestClient) -> None:
    response = auth_client.post("/api/v1/projects/", json={"name": f"project-{uuid4()}"})
    assert response.status_code == 201
    body = response.json()
    assert set(body) == _SUCCESS_ENVELOPE_KEYS
    assert body["code"] == 0
    assert "deleted_at" not in body["data"]


def test_validation_error_shape(auth_client: TestClient) -> None:
    response = auth_client.post("/api/v1/projects/", json={"name": ""})
    assert response.status_code == 422
    body = _assert_error_envelope(response.json())
    assert body["code"] == BizCode.VALIDATION_ERROR
    assert isinstance(body["details"], list)
    assert body["details"]
    assert body["request_id"]
    assert response.headers["x-request-id"] == body["request_id"]


def test_not_found_shape(auth_client: TestClient) -> None:
    response = auth_client.get(f"/api/v1/projects/{uuid4()}")
    assert response.status_code == 404
    body = _assert_error_envelope(response.json())
    assert body["code"] == ProjectCode.NOT_FOUND
    assert body["message"] == "项目不存在"
    assert body["details"] == []
    assert body["request_id"]


def test_duplicate_name_conflict_shape(auth_client: TestClient) -> None:
    name = f"project-{uuid4()}"
    created = auth_client.post("/api/v1/projects/", json={"name": name})
    assert created.status_code == 201

    conflicted = auth_client.post("/api/v1/projects/", json={"name": name})
    assert conflicted.status_code == 409
    body = _assert_error_envelope(conflicted.json())
    assert body["code"] == ProjectCode.NAME_CONFLICT
    assert body["message"] == "项目名称已存在"


def test_unmapped_integrity_error_is_500_not_409(
    auth_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """NOT NULL / 外键违约是代码 bug，不能当成客户端 409。"""

    class _Diag:
        constraint_name = "ck_projects_not_registered"

    class _Orig(Exception):
        diag = _Diag()

    def boom(*args: object, **kwargs: object) -> None:
        raise IntegrityError("INSERT ...", None, _Orig())

    monkeypatch.setattr(project_service, "create_project", boom)
    response = auth_client.post("/api/v1/projects/", json={"name": f"project-{uuid4()}"})
    assert response.status_code == 500
    body = _assert_error_envelope(response.json())
    assert body["code"] == BizCode.INTERNAL_ERROR
    # 对外只给通用文案，SQL 和约束名只进日志
    assert body["message"] == "服务器内部错误"


def test_openapi_success_data_is_required_ref(client: TestClient) -> None:
    spec = client.get("/openapi.json").json()
    schemas = spec["components"]["schemas"]

    project_read = schemas["ProjectRead"]["properties"]
    assert {"id", "name", "created_at"} <= set(project_read)
    assert "deleted_at" not in project_read

    created = spec["paths"]["/api/v1/projects/"]["post"]["responses"]["201"]
    envelope_ref = created["content"]["application/json"]["schema"]["$ref"]
    envelope = schemas[envelope_ref.rsplit("/", 1)[-1]]
    assert "data" in envelope["required"]
    assert envelope["properties"]["data"]["$ref"].endswith("/ProjectRead")


def test_openapi_scopes_error_responses_to_real_routes(client: TestClient) -> None:
    spec = client.get("/openapi.json").json()
    health = spec["paths"]["/api/v1/health"]["get"]["responses"]
    assert "409" not in health
    assert "404" not in health
    assert "401" not in health

    post_projects = spec["paths"]["/api/v1/projects/"]["post"]["responses"]
    assert "409" in post_projects
    assert "401" in post_projects
