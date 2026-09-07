from uuid import uuid4

from fastapi.testclient import TestClient


def test_create_then_get(client: TestClient) -> None:
    name = f"project-{uuid4()}"
    created = client.post("/api/v1/projects/", json={"name": name})
    assert created.status_code == 201
    envelope = created.json()
    assert envelope["code"] == 0
    body = envelope["data"]
    assert body["name"] == name
    project_id = body["id"]

    fetched = client.get(f"/api/v1/projects/{project_id}")
    assert fetched.status_code == 200
    assert fetched.json()["data"]["id"] == project_id
    assert fetched.json()["data"]["name"] == name


def test_soft_delete_hides_from_list(client: TestClient) -> None:
    name = f"project-{uuid4()}"
    created = client.post("/api/v1/projects/", json={"name": name})
    assert created.status_code == 201
    project_id = created.json()["data"]["id"]

    deleted = client.delete(f"/api/v1/projects/{project_id}")
    assert deleted.status_code == 204

    listed = client.get("/api/v1/projects/")
    assert listed.status_code == 200
    assert project_id not in [row["id"] for row in listed.json()["data"]["items"]]

    fetched = client.get(f"/api/v1/projects/{project_id}")
    assert fetched.status_code == 404


def test_list_is_paginated(client: TestClient) -> None:
    created_ids = []
    for _ in range(3):
        created = client.post(
            "/api/v1/projects/", json={"name": f"project-{uuid4()}"}
        )
        assert created.status_code == 201
        created_ids.append(created.json()["data"]["id"])

    page1 = client.get("/api/v1/projects/", params={"page": 1, "page_size": 2})
    assert page1.status_code == 200
    data = page1.json()["data"]
    assert set(data) == {"items", "total", "page", "page_size"}
    assert data["page"] == 1
    assert data["page_size"] == 2
    assert data["total"] == 3
    assert len(data["items"]) == 2
    assert {row["id"] for row in data["items"]} <= set(created_ids)

    page2 = client.get("/api/v1/projects/", params={"page": 2, "page_size": 2})
    assert page2.status_code == 200
    assert page2.json()["data"]["total"] == 3
    assert len(page2.json()["data"]["items"]) == 1


def test_illegal_sort_is_422(client: TestClient) -> None:
    response = client.get("/api/v1/projects/", params={"sort": "deleted_at"})
    assert response.status_code == 422


def test_page_size_over_limit_is_422(client: TestClient) -> None:
    response = client.get("/api/v1/projects/", params={"page_size": 101})
    assert response.status_code == 422
