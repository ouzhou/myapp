from contextvars import ContextVar
from uuid import UUID

from pydantic import BaseModel, Field


class CurrentUser(BaseModel):
    """请求身份。不是 ORM 实体；第 14 步接 Logto 时这个形状不变。"""

    user_id: UUID
    tenant_id: UUID
    membership_id: UUID | None = None
    permissions: list[str] = Field(default_factory=list)
    is_platform_admin: bool = False


current_user_ctx: ContextVar[CurrentUser | None] = ContextVar(
    "current_user", default=None
)
request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)
client_ip_ctx: ContextVar[str | None] = ContextVar("client_ip", default=None)
