from uuid import uuid4

from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import BizCode
from app.modules.users.models import User
from tests.conftest import (
    LOGTO_AUDIENCE,
    jwt_headers,
    sign_access_token,
)


def test_expired_token_is_401(client: TestClient, db_session: Session) -> None:
    headers = jwt_headers(db_session)
    token = sign_access_token(
        sub=f"user_{headers['X-User-Id']}", exp_delta_seconds=-10
    )
    response = client.get(
        "/api/v1/projects/",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-Id": headers["X-Tenant-Id"],
        },
    )
    assert response.status_code == 401
    assert response.json()["code"] == BizCode.UNAUTHORIZED


def test_wrong_signature_is_401(client: TestClient, db_session: Session) -> None:
    headers = jwt_headers(db_session)
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    token = sign_access_token(
        sub=f"user_{headers['X-User-Id']}", private_key=other_key
    )
    response = client.get(
        "/api/v1/projects/",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-Id": headers["X-Tenant-Id"],
        },
    )
    assert response.status_code == 401


def test_wrong_audience_is_401(client: TestClient, db_session: Session) -> None:
    headers = jwt_headers(db_session)
    token = sign_access_token(
        sub=f"user_{headers['X-User-Id']}",
        audience="https://other-api.example",
    )
    response = client.get(
        "/api/v1/projects/",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-Id": headers["X-Tenant-Id"],
        },
    )
    assert response.status_code == 401
    assert LOGTO_AUDIENCE != "https://other-api.example"


def test_missing_authorization_is_401(client: TestClient) -> None:
    response = client.get("/api/v1/projects/")
    assert response.status_code == 401


def test_token_tenant_claim_is_ignored(
    client: TestClient, db_session: Session
) -> None:
    headers = jwt_headers(
        db_session,
        extra_claims={"tenant_id": str(uuid4()), "organization_id": "org_x"},
    )
    listed = client.get(
        "/api/v1/projects/",
        headers={
            "Authorization": headers["Authorization"],
        },
    )
    assert listed.status_code == 200


def test_jit_user_is_authenticated_but_has_no_tenant(
    client: TestClient, db_session: Session
) -> None:
    sub = f"jit_{uuid4()}"
    token = sign_access_token(sub=sub, extra={"email": f"{sub}@idp.example"})
    me = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["data"]["tenants"] == []
    assert me.json()["data"]["current_tenant"] is None

    projects = client.get(
        "/api/v1/projects/",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert projects.status_code == 403
    assert projects.json()["message"] == "无权访问该租户"

    created = db_session.scalars(
        select(User).where(User.idp_subject == sub, User.deleted_at.is_(None))
    ).one()
    assert created.email == f"{sub}@idp.example"
