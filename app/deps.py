from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.context import CurrentUser, current_user_ctx
from app.core.exceptions import AppError, BizCode
from app.db.session import get_db
from app.modules.iam.service import list_permissions_for_membership
from app.modules.users.service import require_user, resolve_membership

DbSession = Annotated[Session, Depends(get_db)]


class HeaderIdentity(BaseModel):
    user_id: UUID
    requested_tenant_id: UUID | None = None


def get_header_identity(
    x_user_id: Annotated[UUID | None, Header()] = None,
    x_tenant_id: Annotated[UUID | None, Header()] = None,
) -> HeaderIdentity:
    if not get_settings().header_auth_enabled or x_user_id is None:
        raise AppError(BizCode.UNAUTHORIZED, "未认证")
    return HeaderIdentity(
        user_id=x_user_id,
        requested_tenant_id=x_tenant_id,
    )


HeaderIdentityDep = Annotated[HeaderIdentity, Depends(get_header_identity)]


def get_current_user(
    db: DbSession,
    identity: HeaderIdentityDep,
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
