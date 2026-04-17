"""merge_branches

Revision ID: 917914e3b0f7
Revises: i9j0k1l2m3n4, j1k2l3m4n5o6
Create Date: 2026-04-17 02:32:06.498510

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '917914e3b0f7'
down_revision: Union[str, Sequence[str], None] = ('i9j0k1l2m3n4', 'j1k2l3m4n5o6')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
