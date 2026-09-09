from __future__ import annotations

import os
import re
from collections.abc import Iterator
from datetime import datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session

_DEFAULT_TEST_URL = "postgresql+psycopg://myapp:myapp@localhost:5432/myapp_test"
_SAFE_DB_NAME = re.compile(r"^[a-zA-Z0-9_]+$")

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", _DEFAULT_TEST_URL)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ.setdefault("LOGTO_ENDPOINT", "http://localhost:3001")
os.environ.setdefault("LOGTO_AUDIENCE", "https://api.myapp.com")

import jwt  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.security import issuer_of, set_decode_key_override  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import app  # noqa: E402

_TEST_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
set_decode_key_override(_TEST_PRIVATE_KEY.public_key())
LOGTO_ENDPOINT = os.environ["LOGTO_ENDPOINT"]
LOGTO_AUDIENCE = os.environ["LOGTO_AUDIENCE"]


def _ensure_database(url: str) -> None:
    sa_url = make_url(url)
    db_name = sa_url.database
    if db_name is None or _SAFE_DB_NAME.match(db_name) is None:
        raise RuntimeError(f"refusing to create database from url: {url}")

    admin_engine = create_engine(
        sa_url.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
    )
    try:
        with admin_engine.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": db_name},
            ).scalar()
            if exists is None:
                conn.execute(text(f"CREATE DATABASE {db_name}"))
    finally:
        admin_engine.dispose()


def _upgrade_schema() -> None:
    from alembic import command
    from alembic.config import Config

    from app.core.config import get_settings

    get_settings.cache_clear()
    command.upgrade(Config("alembic.ini"), "head")


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    _ensure_database(TEST_DATABASE_URL)
    _upgrade_schema()
    test_engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
    yield test_engine
    test_engine.dispose()


@pytest.fixture
def db_session(engine: Engine) -> Iterator[Session]:
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(
        bind=connection,
        autoflush=False,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


def ensure_identity(
    db: Session,
    *,
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
    email: str | None = None,
    display_name: str = "测试用户",
    is_platform_admin: bool = False,
    last_selected_tenant_id: UUID | None = None,
    membership_created_at: datetime | None = None,
    role_code: str | None = "tenant_admin",
) -> tuple[UUID, UUID, UUID]:
    from app.core.permissions import Perm
    from app.modules.iam.models import Role
    from app.modules.iam.service import (
        ensure_custom_role,
        ensure_membership_role_by_code,
    )
    from app.modules.tenants.schemas import TenantCreate
    from app.modules.tenants.service import get_or_create_tenant
    from app.modules.users.schemas import UserCreate
    from app.modules.users.service import get_or_create_membership, get_or_create_user

    resolved_user_id = user_id or uuid4()
    resolved_tenant_id = tenant_id or uuid4()
    tenant = get_or_create_tenant(
        db,
        TenantCreate(slug=f"t-{resolved_tenant_id.hex[:12]}", name="测试租户"),
        tenant_id=resolved_tenant_id,
    )
    user = get_or_create_user(
        db,
        UserCreate(
            email=email or f"user-{resolved_user_id.hex}@example.test",
            display_name=display_name,
            is_platform_admin=is_platform_admin,
            idp_subject=f"user_{resolved_user_id}",
        ),
        user_id=resolved_user_id,
    )
    if user.idp_subject is None:
        user.idp_subject = f"user_{user.id}"
    if last_selected_tenant_id is not None:
        user.last_selected_tenant_id = last_selected_tenant_id
    membership = get_or_create_membership(
        db,
        user_id=user.id,
        tenant_id=tenant.id,
        created_at=membership_created_at,
    )
    if role_code is not None:
        if role_code != Role.CODE_TENANT_ADMIN:
            ensure_custom_role(
                db,
                membership.tenant_id,
                code=role_code,
                name=role_code,
                permissions=(Perm.PROJECT_READ,),
            )
        ensure_membership_role_by_code(db, membership, role_code)
    db.flush()
    return user.id, tenant.id, membership.id


def auth_headers(
    db: Session,
    *,
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
    is_platform_admin: bool = False,
    include_tenant: bool = True,
    last_selected_tenant_id: UUID | None = None,
    membership_created_at: datetime | None = None,
    role_code: str | None = "tenant_admin",
) -> dict[str, str]:
    resolved_user_id, resolved_tenant_id, _membership_id = ensure_identity(
        db,
        user_id=user_id,
        tenant_id=tenant_id,
        is_platform_admin=is_platform_admin,
        last_selected_tenant_id=last_selected_tenant_id,
        membership_created_at=membership_created_at,
        role_code=role_code,
    )
    headers = {"X-User-Id": str(resolved_user_id)}
    if include_tenant:
        headers["X-Tenant-Id"] = str(resolved_tenant_id)
    return headers


def sign_access_token(
    *,
    sub: str,
    audience: str | None = None,
    issuer: str | None = None,
    exp_delta_seconds: int = 3600,
    extra: dict[str, object] | None = None,
    private_key: RSAPrivateKey | None = None,
) -> str:
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)
    payload: dict[str, object] = {
        "sub": sub,
        "iss": issuer or issuer_of(LOGTO_ENDPOINT),
        "aud": audience or LOGTO_AUDIENCE,
        "iat": now,
        "exp": now + timedelta(seconds=exp_delta_seconds),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, private_key or _TEST_PRIVATE_KEY, algorithm="RS256")


def jwt_headers(
    db: Session,
    *,
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
    is_platform_admin: bool = False,
    include_tenant: bool = True,
    last_selected_tenant_id: UUID | None = None,
    membership_created_at: datetime | None = None,
    role_code: str | None = "tenant_admin",
    extra_claims: dict[str, object] | None = None,
) -> dict[str, str]:
    resolved_user_id, resolved_tenant_id, _membership_id = ensure_identity(
        db,
        user_id=user_id,
        tenant_id=tenant_id,
        is_platform_admin=is_platform_admin,
        last_selected_tenant_id=last_selected_tenant_id,
        membership_created_at=membership_created_at,
        role_code=role_code,
    )
    headers = {
        "Authorization": f"Bearer {sign_access_token(sub=f'user_{resolved_user_id}', extra=extra_claims)}",
        "X-User-Id": str(resolved_user_id),
    }
    if include_tenant:
        headers["X-Tenant-Id"] = str(resolved_tenant_id)
    return headers


@pytest.fixture
def client(db_session: Session) -> Iterator[TestClient]:
    # 不要在这里抄一份 get_db 的 commit/rollback：commit 只归 get_db 所有，
    # 测试的隔离由 db_session 外层事务回滚负责。
    def override_get_db() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def auth_client(client: TestClient, db_session: Session) -> TestClient:
    client.headers.update(auth_headers(db_session))
    return client
