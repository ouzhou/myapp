from __future__ import annotations

import uuid

from sqlalchemy import Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, SoftDeleteMixin, TimestampMixin


class Project(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "projects"
    __table_args__ = (
        Index(
            "uq_projects_name_active",
            "name",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str | None] = mapped_column(String(32), nullable=True)
