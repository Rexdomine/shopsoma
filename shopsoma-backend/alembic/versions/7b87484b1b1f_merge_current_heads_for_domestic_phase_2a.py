"""merge current heads for domestic phase 2a

Revision ID: 7b87484b1b1f
Revises: f6a7b8c9d0e1, j6k7l8m9n0p1
Create Date: 2026-07-15 19:26:52.166371

"""

from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "7b87484b1b1f"
down_revision: Union[str, Sequence[str], None] = (
    "f6a7b8c9d0e1",
    "j6k7l8m9n0p1",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
