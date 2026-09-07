from contextvars import ContextVar
from uuid import UUID

from pydantic import BaseModel, Field


class CurrentUser(BaseModel):
    """请求身份。不是 ORM 实体；第 13 步换 JWT 时这个形状不变。"""

    user_id: UUID
    tenant_id: UUID
    roles: list[str] = Field(default_factory=list)


current_user_ctx: ContextVar[CurrentUser | None] = ContextVar(
    "current_user", default=None
)
