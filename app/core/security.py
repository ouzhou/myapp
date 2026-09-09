from functools import lru_cache
from typing import Any

import jwt
from jwt import PyJWKClient

from app.core.config import get_settings
from app.core.exceptions import AppError, BizCode

ALLOWED_ALGORITHMS = ("RS256", "ES384")

_decode_key_override: Any = None


def set_decode_key_override(key: Any | None) -> None:
    """测试用：把取公钥换成本地密钥，不连真 JWKS。"""
    global _decode_key_override
    _decode_key_override = key


def issuer_of(endpoint: str) -> str:
    return f"{endpoint.rstrip('/')}/oidc"


def jwks_url_of(endpoint: str) -> str:
    return f"{issuer_of(endpoint)}/jwks"


@lru_cache
def _jwks_client(endpoint: str) -> PyJWKClient:
    return PyJWKClient(jwks_url_of(endpoint))


def _signing_key(token: str) -> Any:
    if _decode_key_override is not None:
        return _decode_key_override
    settings = get_settings()
    if not settings.logto_endpoint:
        raise AppError(BizCode.UNAUTHORIZED, "未认证")
    return _jwks_client(settings.logto_endpoint).get_signing_key_from_jwt(token).key


def decode_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    if not settings.logto_endpoint or not settings.logto_audience:
        raise AppError(BizCode.UNAUTHORIZED, "未认证")
    try:
        claims = jwt.decode(
            token,
            _signing_key(token),
            algorithms=list(ALLOWED_ALGORITHMS),
            audience=settings.logto_audience,
            issuer=issuer_of(settings.logto_endpoint),
        )
    except jwt.InvalidTokenError as exc:
        raise AppError(BizCode.UNAUTHORIZED, "未认证") from exc
    if not isinstance(claims, dict):
        raise AppError(BizCode.UNAUTHORIZED, "未认证")
    return claims
