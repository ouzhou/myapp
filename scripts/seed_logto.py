"""开发种子：在 Logto 建可登录账号，再绑到本库 users.idp_subject。

测试不要跑这个文件。pytest 继续用 scripts.seed.seed_demo。

    uv run python scripts/seed_logto.py

缺 M2M 配置时会退出。到 http://localhost:3002 建 Machine-to-machine 应用，
勾「Logto Management API access」，把 App ID / Secret 写进 .env。
"""

from __future__ import annotations

import json
import sys
from base64 import b64encode
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.db.session import SessionLocal
from app.modules.users.models import User
from scripts.seed import (
    DEMO_ADMIN_EMAIL,
    DEMO_ADMIN_USERNAME,
    DEMO_MEMBER_EMAIL,
    DEMO_MEMBER_USERNAME,
    DEMO_PLATFORM_EMAIL,
    DEMO_PLATFORM_USERNAME,
    seed_demo,
)

_DEFAULT_MANAGEMENT_RESOURCE = "https://default.logto.app/api"
_SIGN_IN_CSS_PATH = Path(__file__).with_name("logto_sign_in.css")
_SIGN_IN_PRIMARY = "#171717"
_SIGN_IN_DARK_PRIMARY = "#f5f5f5"


class SeedLogtoSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    logto_endpoint: str = ""
    logto_m2m_app_id: str = ""
    logto_m2m_app_secret: str = ""
    logto_seed_password: str = ""
    logto_management_api_resource: str = _DEFAULT_MANAGEMENT_RESOURCE


class SeedLogtoError(RuntimeError):
    pass


def _require(settings: SeedLogtoSettings) -> None:
    missing: list[str] = []
    if not settings.logto_endpoint.strip():
        missing.append("LOGTO_ENDPOINT")
    if not settings.logto_m2m_app_id.strip():
        missing.append("LOGTO_M2M_APP_ID")
    if not settings.logto_m2m_app_secret.strip():
        missing.append("LOGTO_M2M_APP_SECRET")
    if not settings.logto_seed_password.strip():
        missing.append("LOGTO_SEED_PASSWORD")
    if missing:
        raise SeedLogtoError(
            "缺少 "
            + "、".join(missing)
            + "。到 http://localhost:3002 建 Machine-to-machine 应用，"
            "勾 Logto Management API access，再写进 .env。"
        )


def _request(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    json_body: dict[str, Any] | None = None,
    form: dict[str, str] | None = None,
) -> Any:
    payload: bytes | None = None
    req_headers = dict(headers or {})
    if json_body is not None:
        payload = json.dumps(json_body).encode()
        req_headers["Content-Type"] = "application/json"
    elif form is not None:
        payload = urlencode(form).encode()
        req_headers["Content-Type"] = "application/x-www-form-urlencoded"
    request = Request(url, data=payload, headers=req_headers, method=method)
    try:
        with urlopen(request) as response:
            raw = response.read()
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SeedLogtoError(f"{method} {url} -> HTTP {exc.code}: {body}") from exc
    except URLError as exc:
        raise SeedLogtoError(f"无法连接 Logto：{url} ({exc.reason})") from exc
    if not raw:
        return None
    return json.loads(raw.decode())


def fetch_management_token(settings: SeedLogtoSettings) -> str:
    endpoint = settings.logto_endpoint.rstrip("/")
    basic = b64encode(
        f"{settings.logto_m2m_app_id}:{settings.logto_m2m_app_secret}".encode()
    ).decode()
    data = _request(
        "POST",
        f"{endpoint}/oidc/token",
        headers={"Authorization": f"Basic {basic}"},
        form={
            "grant_type": "client_credentials",
            "resource": settings.logto_management_api_resource,
            "scope": "all",
        },
    )
    if not isinstance(data, dict):
        raise SeedLogtoError("Logto token 响应不是对象")
    token = data.get("access_token")
    if not isinstance(token, str) or not token:
        raise SeedLogtoError("Logto token 响应没有 access_token")
    return token


def _api(settings: SeedLogtoSettings, token: str, method: str, path: str, **kwargs: Any) -> Any:
    endpoint = settings.logto_endpoint.rstrip("/")
    return _request(
        method,
        f"{endpoint}{path}",
        headers={"Authorization": f"Bearer {token}"},
        **kwargs,
    )


def find_user_id(
    settings: SeedLogtoSettings, token: str, *, username: str
) -> str | None:
    data = _api(
        settings,
        token,
        "GET",
        f"/api/users?{urlencode({'search.username': username, 'page': 1, 'page_size': 20})}",
    )
    rows: list[Any]
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict) and isinstance(data.get("data"), list):
        rows = data["data"]
    else:
        raise SeedLogtoError("GET /api/users 响应格式无法识别")
    for row in rows:
        if isinstance(row, dict) and row.get("username") == username:
            user_id = row.get("id")
            if isinstance(user_id, str) and user_id:
                return user_id
    return None


def ensure_logto_user(
    settings: SeedLogtoSettings,
    token: str,
    *,
    username: str,
    email: str,
    name: str,
) -> str:
    existing = find_user_id(settings, token, username=username)
    if existing is not None:
        return existing
    created = _api(
        settings,
        token,
        "POST",
        "/api/users",
        json_body={
            "username": username,
            "primaryEmail": email,
            "password": settings.logto_seed_password,
            "name": name,
        },
    )
    if not isinstance(created, dict):
        raise SeedLogtoError("POST /api/users 响应不是对象")
    user_id = created.get("id")
    if not isinstance(user_id, str) or not user_id:
        raise SeedLogtoError("POST /api/users 没有返回 id")
    return user_id


def apply_sign_in_experience(settings: SeedLogtoSettings, token: str) -> None:
    css = _SIGN_IN_CSS_PATH.read_text(encoding="utf-8")
    _api(
        settings,
        token,
        "PATCH",
        "/api/sign-in-exp",
        json_body={
            "color": {
                "primaryColor": _SIGN_IN_PRIMARY,
                "isDarkModeEnabled": False,
                "darkPrimaryColor": _SIGN_IN_DARK_PRIMARY,
            },
            "customCss": css,
        },
    )


def bind_idp_subject(db: Session, *, email: str, idp_subject: str) -> None:
    user = db.scalars(
        select(User).where(User.email == email, User.deleted_at.is_(None))
    ).first()
    if user is None:
        raise SeedLogtoError(f"本库没有邮箱 {email} 的用户")
    if user.idp_subject == idp_subject:
        return
    user.idp_subject = idp_subject
    db.flush()


def seed_logto(db: Session, settings: SeedLogtoSettings) -> None:
    _require(settings)
    token = fetch_management_token(settings)
    apply_sign_in_experience(settings, token)
    platform_id = ensure_logto_user(
        settings,
        token,
        username=DEMO_PLATFORM_USERNAME,
        email=DEMO_PLATFORM_EMAIL,
        name="平台管理员",
    )
    admin_id = ensure_logto_user(
        settings,
        token,
        username=DEMO_ADMIN_USERNAME,
        email=DEMO_ADMIN_EMAIL,
        name="租户管理员",
    )
    member_id = ensure_logto_user(
        settings,
        token,
        username=DEMO_MEMBER_USERNAME,
        email=DEMO_MEMBER_EMAIL,
        name="普通成员",
    )
    seed_demo(db)
    bind_idp_subject(db, email=DEMO_PLATFORM_EMAIL, idp_subject=platform_id)
    bind_idp_subject(db, email=DEMO_ADMIN_EMAIL, idp_subject=admin_id)
    bind_idp_subject(db, email=DEMO_MEMBER_EMAIL, idp_subject=member_id)


def main() -> None:
    settings = SeedLogtoSettings()
    session = SessionLocal()
    try:
        seed_logto(session, settings)
        session.commit()
    except SeedLogtoError as exc:
        session.rollback()
        print(exc, file=sys.stderr)
        raise SystemExit(1) from exc
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
    print(
        "已同步 Logto 开发账号："
        f"{DEMO_PLATFORM_USERNAME} / {DEMO_ADMIN_USERNAME} / {DEMO_MEMBER_USERNAME}"
        "（密码见 LOGTO_SEED_PASSWORD）"
    )


if __name__ == "__main__":
    main()
