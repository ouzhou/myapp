"""add project tenant_id

Revision ID: 76707740789c
Revises: 800e5ec06b1f
Create Date: 2026-09-08 00:15:31.950777

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '76707740789c'
down_revision: Union[str, Sequence[str], None] = '800e5ec06b1f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_LEGACY_TENANT_ID = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("projects", sa.Column("tenant_id", sa.Uuid(), nullable=True))
    op.execute(
        sa.text(
            f"UPDATE projects SET tenant_id = '{_LEGACY_TENANT_ID}' "
            "WHERE tenant_id IS NULL"
        )
    )
    op.alter_column("projects", "tenant_id", existing_type=sa.Uuid(), nullable=False)
    op.drop_index(
        "uq_projects_name_active",
        table_name="projects",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "uq_projects_tenant_id_name_active",
        "projects",
        ["tenant_id", "name"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "ix_projects_tenant_id_created_at",
        "projects",
        ["tenant_id", "created_at"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_projects_tenant_id_created_at", table_name="projects")
    op.drop_index(
        "uq_projects_tenant_id_name_active",
        table_name="projects",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "uq_projects_name_active",
        "projects",
        ["name"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.drop_column("projects", "tenant_id")
