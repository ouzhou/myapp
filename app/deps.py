from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.context import CurrentUser, current_user_ctx
from app.core.exceptions import AppError, BizCode
from app.core.security import decode_access_token
from app.db.session import get_db
from app.modules.iam.service import list_permissions_for_membership
from app.modules.users.models import User
from app.modules.users.service import require_user, resolve_idp_user, resolve_membership

DbSession = Annotated[Session, Depends(get_db)]
_bearer_scheme = HTTPBearer(auto_error=False)


class AuthIdentity(BaseModel):
    user_id: UUID
    requested_tenant_id: UUID | None = None


def get_auth_identity(
    db: DbSession,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)
    ] = None,
    x_user_id: Annotated[UUID | None, Header()] = None,
    x_tenant_id: Annotated[UUID | None, Header()] = None,
) -> AuthIdentity:
    if credentials is not None and credentials.credentials:
        claims = decode_access_token(credentials.credentials)
        user = resolve_idp_user(db, claims)
        return AuthIdentity(user_id=user.id, requested_tenant_id=x_tenant_id)
    if get_settings().header_auth_enabled and x_user_id is not None:
        return AuthIdentity(user_id=x_user_id, requested_tenant_id=x_tenant_id)
    raise AppError(BizCode.UNAUTHORIZED, "未认证")


HeaderIdentity = AuthIdentity
HeaderIdentityDep = Annotated[AuthIdentity, Depends(get_auth_identity)]
AuthIdentityDep = HeaderIdentityDep


def get_current_user(
    db: DbSession,
    identity: AuthIdentityDep,
) -> CurrentUser:
    user = require_user(db, identity.user_id)
    membership = resolve_membership(db, user, identity.requested_tenant_id)
    current = CurrentUser(
        user_id=user.id,
        tenant_id=membership.tenant_id,
        membership_id=membership.id,
        permissions=list_permissions_for_membership(db, membership.id),
        is_platform_admin=user.is_platform_admin,
    )
    current_user_ctx.set(current)
    return current


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]


def require_platform_admin(
    db: DbSession,
    identity: AuthIdentityDep,
) -> User:
    user = require_user(db, identity.user_id)
    if not user.is_platform_admin:
        raise AppError(BizCode.FORBIDDEN, "没有权限")
    return user


PlatformAdminDep = Annotated[User, Depends(require_platform_admin)]
