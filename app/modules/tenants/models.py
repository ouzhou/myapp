from __future__ import annotations

import uuid

from sqlalchemy import Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, SoftDeleteMixin, TimestampMixin


class Tenant(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "tenants"
    __table_args__ = (
        Index(
            "uq_tenants_slug_active",
            "slug",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    STATUS_ACTIVE = "active"
    STATUS_DISABLED = "disabled"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=STATUS_ACTIVE,
    )
