"""empty schema

Revision ID: c30a8120fd83
Revises:
Create Date: 2026-09-07 14:08:16.238618

"""
from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "c30a8120fd83"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
