from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.modules.tenants.schemas import TenantSummary


class UserProfile(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    display_name: str
    status: str
    is_platform_admin: bool


class MeRead(BaseModel):
    user: UserProfile
    tenants: list[TenantSummary]
    current_tenant: TenantSummary | None


class CurrentTenantUpdate(BaseModel):
    tenant_id: UUID


class UserCreate(BaseModel):
    email: str = Field(min_length=1, max_length=255)
    display_name: str = Field(min_length=1, max_length=255)
    status: str = "active"
    is_platform_admin: bool = False
    idp_subject: str | None = None
