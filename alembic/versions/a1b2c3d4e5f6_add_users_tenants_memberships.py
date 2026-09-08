"""add users tenants memberships

Revision ID: a1b2c3d4e5f6
Revises: 2da3f2368c41
Create Date: 2026-09-08 09:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "2da3f2368c41"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tenants")),
    )
    op.create_index(
        "uq_tenants_slug_active",
        "tenants",
        ["slug"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.execute(
        sa.text(
            """
            INSERT INTO tenants (id, slug, name, status, created_at, updated_at)
            SELECT DISTINCT
                tenant_id,
                'legacy-' || replace(tenant_id::text, '-', ''),
                'Legacy',
                'active',
                now(),
                now()
            FROM (
                SELECT tenant_id FROM projects
                UNION
                SELECT tenant_id FROM audit_logs
            ) src
            """
        )
    )

    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("is_platform_admin", sa.Boolean(), nullable=False),
        sa.Column("idp_subject", sa.String(length=255), nullable=True),
        sa.Column("last_selected_tenant_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["last_selected_tenant_id"],
            ["tenants.id"],
            name=op.f("fk_users_last_selected_tenant_id_tenants"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
    )
    op.create_index(
        "uq_users_email_active",
        "users",
        ["email"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "uq_users_idp_subject_active",
        "users",
        ["idp_subject"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL AND idp_subject IS NOT NULL"),
    )

    op.create_table(
        "memberships",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_memberships_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_memberships_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_memberships")),
    )
    op.create_index(
        "uq_memberships_user_id_tenant_id",
        "memberships",
        ["user_id", "tenant_id"],
        unique=True,
    )
    op.create_index(
        "ix_memberships_user_id_created_at",
        "memberships",
        ["user_id", "created_at"],
    )

    op.create_foreign_key(
        op.f("fk_projects_tenant_id_tenants"),
        "projects",
        "tenants",
        ["tenant_id"],
        ["id"],
    )
    op.create_foreign_key(
        op.f("fk_audit_logs_tenant_id_tenants"),
        "audit_logs",
        "tenants",
        ["tenant_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_audit_logs_tenant_id_tenants"),
        "audit_logs",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("fk_projects_tenant_id_tenants"),
        "projects",
        type_="foreignkey",
    )
    op.drop_index("ix_memberships_user_id_created_at", table_name="memberships")
    op.drop_index("uq_memberships_user_id_tenant_id", table_name="memberships")
    op.drop_table("memberships")
    op.drop_index(
        "uq_users_idp_subject_active",
        table_name="users",
        postgresql_where=sa.text("deleted_at IS NULL AND idp_subject IS NOT NULL"),
    )
    op.drop_index(
        "uq_users_email_active",
        table_name="users",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.drop_table("users")
    op.drop_index(
        "uq_tenants_slug_active",
        table_name="tenants",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.drop_table("tenants")
