from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.permissions import Perm
from app.modules.users.schemas import UserProfile


class PermissionRead(BaseModel):
    code: str


class RoleCreate(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    permissions: list[Perm] = Field(default_factory=list)


class RoleUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=64)
    name: str | None = Field(default=None, min_length=1, max_length=255)


class RolePermissionsUpdate(BaseModel):
    permissions: list[Perm]


class RoleSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    name: str
    is_system: bool


class RoleRead(BaseModel):
    id: UUID
    tenant_id: UUID
    code: str
    name: str
    is_system: bool
    permissions: list[str]
    created_at: datetime
    updated_at: datetime


class MemberCreate(BaseModel):
    email: str = Field(min_length=1, max_length=255)
    display_name: str = Field(min_length=1, max_length=255)
    role_ids: list[UUID] = Field(default_factory=list)


class MemberRolesUpdate(BaseModel):
    role_ids: list[UUID]


class MemberRead(BaseModel):
    id: UUID
    tenant_id: UUID
    user: UserProfile
    roles: list[RoleSummary]
    status: str
    created_at: datetime
    updated_at: datetime
