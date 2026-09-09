"""collapse system roles into tenant_admin

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-09-08 16:50:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d5e6f7a8b9c0"
down_revision: Union[str, Sequence[str], None] = "c4d5e6f7a8b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE roles
            SET code = 'tenant_admin', name = '租户管理员'
            WHERE is_system IS TRUE AND code = 'owner'
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE roles
            SET is_system = FALSE
            WHERE is_system IS TRUE AND code IN ('admin', 'member')
            """
        )
    )
    op.execute(
        sa.text(
            """
            DELETE FROM role_permissions
            WHERE role_id IN (SELECT id FROM roles WHERE is_system IS TRUE)
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE roles
            SET code = 'owner', name = '拥有者'
            WHERE is_system IS TRUE AND code = 'tenant_admin'
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE roles
            SET is_system = TRUE
            WHERE code IN ('admin', 'member')
            """
        )
    )
