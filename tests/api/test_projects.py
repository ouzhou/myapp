from uuid import uuid4

from fastapi.testclient import TestClient


def test_create_then_get(client: TestClient) -> None:
    name = f"project-{uuid4()}"
    created = client.post("/api/v1/projects/", json={"name": name})
    assert created.status_code == 201
    body = created.json()
    assert body["name"] == name
    project_id = body["id"]

    fetched = client.get(f"/api/v1/projects/{project_id}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == project_id
    assert fetched.json()["name"] == name


def test_soft_delete_hides_from_list(client: TestClient) -> None:
    name = f"project-{uuid4()}"
    created = client.post("/api/v1/projects/", json={"name": name})
    assert created.status_code == 201
    project_id = created.json()["id"]

    deleted = client.delete(f"/api/v1/projects/{project_id}")
    assert deleted.status_code == 204

    listed = client.get("/api/v1/projects/")
    assert listed.status_code == 200
    assert project_id not in [row["id"] for row in listed.json()]

    fetched = client.get(f"/api/v1/projects/{project_id}")
    assert fetched.status_code == 404
