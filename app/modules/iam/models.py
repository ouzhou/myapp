from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Role(TimestampMixin, Base):
    __tablename__ = "roles"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code"),
        UniqueConstraint("id", "tenant_id"),
    )

    CODE_TENANT_ADMIN = "tenant_admin"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    permission: Mapped[str] = mapped_column(String(64), primary_key=True)


class MembershipRole(Base):
    __tablename__ = "membership_roles"
    __table_args__ = (
        ForeignKeyConstraint(
            ["membership_id", "tenant_id"],
            ["memberships.id", "memberships.tenant_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["role_id", "tenant_id"],
            ["roles.id", "roles.tenant_id"],
            ondelete="CASCADE",
        ),
    )

    membership_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    role_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
