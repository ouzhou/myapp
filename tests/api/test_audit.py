from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.context import CurrentUser
from app.modules.audit.models import AuditLog
from app.modules.projects import service as project_service
from app.modules.projects.schemas import ProjectCreate, ProjectUpdate


def test_update_writes_audit_row(
    auth_client: TestClient, db_session: Session
) -> None:
    request_id = "audit-update-1"
    original_name = f"project-{uuid4()}"
    created = auth_client.post(
        "/api/v1/projects/",
        json={"name": original_name, "description": "before"},
        headers={"X-Request-ID": request_id},
    )
    assert created.status_code == 201
    project_id = UUID(created.json()["data"]["id"])

    renamed = f"renamed-{uuid4()}"
    updated = auth_client.patch(
        f"/api/v1/projects/{project_id}",
        json={"name": renamed},
        headers={"X-Request-ID": request_id},
    )
    assert updated.status_code == 200

    rows = db_session.scalars(
        select(AuditLog).where(
            AuditLog.resource_id == project_id,
            AuditLog.action == "update",
        )
    ).all()
    assert len(rows) == 1
    row = rows[0]
    assert row.user_id == UUID(auth_client.headers["X-User-Id"])
    assert row.tenant_id == UUID(auth_client.headers["X-Tenant-Id"])
    assert row.resource_type == "project"
    assert row.request_id == request_id
    assert row.ip == "testclient"
    assert row.before == {
        "name": original_name,
        "description": "before",
        "status": None,
    }
    assert row.after == {"name": renamed, "description": "before", "status": None}


def test_audit_rolls_back_when_write_fails_after_it(db_session: Session) -> None:
    from tests.conftest import ensure_identity

    user_id, tenant_id, membership_id = ensure_identity(db_session)
    user = CurrentUser(
        user_id=user_id,
        tenant_id=tenant_id,
        membership_id=membership_id,
    )
    created = project_service.create_project(
        db_session, user, ProjectCreate(name=f"project-{uuid4()}")
    )

    nested = db_session.begin_nested()
    try:
        project_service.update_project(
            db_session,
            user,
            created.id,
            ProjectUpdate(name=f"renamed-{uuid4()}"),
        )
        raise RuntimeError("simulated failure after audit")
    except RuntimeError:
        nested.rollback()

    db_session.expire_all()
    remaining = db_session.scalars(
        select(AuditLog).where(AuditLog.resource_id == created.id)
    ).all()
    assert [row.action for row in remaining] == ["create"]
