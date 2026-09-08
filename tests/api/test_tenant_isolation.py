from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.conftest import auth_headers


def test_cross_tenant_is_404_not_403(client: TestClient, db_session: Session) -> None:
    headers_a = auth_headers(db_session)
    headers_b = auth_headers(db_session)
    name = f"project-{uuid4()}"
    created = client.post("/api/v1/projects/", json={"name": name}, headers=headers_a)
    assert created.status_code == 201
    project_id = created.json()["data"]["id"]

    fetched = client.get(f"/api/v1/projects/{project_id}", headers=headers_b)
    assert fetched.status_code == 404
    assert fetched.json()["message"] == "项目不存在"

    updated = client.patch(
        f"/api/v1/projects/{project_id}",
        json={"name": f"hijacked-{uuid4()}"},
        headers=headers_b,
    )
    assert updated.status_code == 404

    deleted = client.delete(f"/api/v1/projects/{project_id}", headers=headers_b)
    assert deleted.status_code == 404

    listed = client.get("/api/v1/projects/", headers=headers_b)
    assert listed.status_code == 200
    assert project_id not in [row["id"] for row in listed.json()["data"]["items"]]

    still_there = client.get(f"/api/v1/projects/{project_id}", headers=headers_a)
    assert still_there.status_code == 200
    assert still_there.json()["data"]["name"] == name


def test_forged_tenant_id_in_body_is_ignored(
    client: TestClient, db_session: Session
) -> None:
    tenant_a = uuid4()
    tenant_b = uuid4()
    headers_a = auth_headers(db_session, tenant_id=tenant_a)
    created = client.post(
        "/api/v1/projects/",
        json={"name": f"project-{uuid4()}", "tenant_id": str(tenant_b)},
        headers=headers_a,
    )
    assert created.status_code == 201
    body = created.json()["data"]
    project_id = body["id"]
    assert body["tenant_id"] == str(tenant_a)

    assert (
        client.get(f"/api/v1/projects/{project_id}", headers=headers_a).status_code
        == 200
    )
    assert (
        client.get(
            f"/api/v1/projects/{project_id}",
            headers=auth_headers(db_session, tenant_id=tenant_b),
        ).status_code
        == 404
    )


def test_same_name_allowed_across_tenants(
    client: TestClient, db_session: Session
) -> None:
    name = f"project-{uuid4()}"
    first = client.post(
        "/api/v1/projects/", json={"name": name}, headers=auth_headers(db_session)
    )
    second = client.post(
        "/api/v1/projects/", json={"name": name}, headers=auth_headers(db_session)
    )
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["data"]["id"] != second.json()["data"]["id"]


def test_same_tenant_duplicate_name_is_still_409(
    client: TestClient, db_session: Session
) -> None:
    headers = auth_headers(db_session)
    name = f"project-{uuid4()}"
    created = client.post("/api/v1/projects/", json={"name": name}, headers=headers)
    conflicted = client.post("/api/v1/projects/", json={"name": name}, headers=headers)
    assert created.status_code == 201
    assert conflicted.status_code == 409
