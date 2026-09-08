from collections.abc import Callable
from enum import StrEnum
from typing import Annotated

from fastapi import Depends

from app.core.context import CurrentUser
from app.core.exceptions import AppError, BizCode


class Perm(StrEnum):
    PROJECT_READ = "project:read"
    PROJECT_WRITE = "project:write"
    ROLE_READ = "role:read"
    ROLE_WRITE = "role:write"
    MEMBER_READ = "member:read"
    MEMBER_WRITE = "member:write"


def require_perm(perm: Perm) -> Callable[..., CurrentUser]:
    from app.deps import get_current_user

    def checker(
        user: Annotated[CurrentUser, Depends(get_current_user)],
    ) -> CurrentUser:
        if perm.value not in user.permissions:
            raise AppError(BizCode.FORBIDDEN, "没有权限")
        return user

    checker.__name__ = f"require_{perm.name.lower()}"
    return checker
