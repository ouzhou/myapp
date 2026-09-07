from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.context import CurrentUser, current_user_ctx
from app.core.exceptions import AppError, BizCode
from app.db.session import get_db

DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(
    x_user_id: Annotated[UUID | None, Header()] = None,
    x_tenant_id: Annotated[UUID | None, Header()] = None,
    x_roles: Annotated[str | None, Header()] = None,
) -> CurrentUser:
    if (
        not get_settings().header_auth_enabled
        or x_user_id is None
        or x_tenant_id is None
    ):
        raise AppError(BizCode.UNAUTHORIZED, "未认证")
    roles = [part.strip() for part in (x_roles or "").split(",") if part.strip()]
    user = CurrentUser(user_id=x_user_id, tenant_id=x_tenant_id, roles=roles)
    current_user_ctx.set(user)
    return user


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
