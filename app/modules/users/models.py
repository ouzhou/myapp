from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, SoftDeleteMixin, TimestampMixin


class User(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        Index(
            "uq_users_email_active",
            "email",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "uq_users_idp_subject_active",
            "idp_subject",
            unique=True,
            postgresql_where=text("deleted_at IS NULL AND idp_subject IS NOT NULL"),
        ),
    )

    STATUS_ACTIVE = "active"
    STATUS_DISABLED = "disabled"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=STATUS_ACTIVE,
    )
    is_platform_admin: Mapped[bool] = mapped_column(nullable=False, default=False)
    idp_subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_selected_tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tenants.id", ondelete="SET NULL"),
        nullable=True,
    )


class Membership(TimestampMixin, Base):
    __tablename__ = "memberships"
    __table_args__ = (
        Index(
            "uq_memberships_user_id_tenant_id",
            "user_id",
            "tenant_id",
            unique=True,
        ),
        UniqueConstraint("id", "tenant_id"),
        Index("ix_memberships_user_id_created_at", "user_id", "created_at"),
    )

    STATUS_ACTIVE = "active"
    STATUS_DISABLED = "disabled"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=STATUS_ACTIVE,
    )
