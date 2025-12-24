"""merge multiple heads

Revision ID: 17d4240dbb35
Revises: 75427e964440, b1c2d3e4f5g6
Create Date: 2025-12-20 20:28:37.677830

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '17d4240dbb35'
down_revision: Union[str, None] = ('75427e964440', 'b1c2d3e4f5g6')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
