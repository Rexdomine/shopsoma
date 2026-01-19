"""clean up men categories to new structure only

Revision ID: d1e2f3a4b5c6
Revises: c2f9a1b4d7e8
Create Date: 2026-01-19 15:45:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "d1e2f3a4b5c6"
down_revision = "c2f9a1b4d7e8"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()

    men_id = conn.execute(
        sa.text("SELECT id FROM categories WHERE slug = 'men' OR name = 'Men' LIMIT 1")
    ).scalar()
    if not men_id:
        return

    allowed_men_slugs = [
        "men-tops",
        "men-tops-t-shirts",
        "men-tops-shirts",
        "men-bottoms",
        "men-bottoms-jeans",
        "men-bottoms-trousers",
        "men-bottoms-shorts",
        "men-activewear",
        "men-activewear-tops",
        "men-activewear-bottoms",
        "men-co-ords",
        "men-shoes",
        "men-shoes-casual",
        "men-shoes-formal",
        "men-accessories",
        "men-accessories-watches-jewellery",
        "men-accessories-wallets",
        "men-accessories-belts",
        "men-accessories-sunglasses",
        "men-accessories-caps-hats",
        "men-outerwear",
        "men-outerwear-hoodies",
    ]

    # Deactivate old Men subcategories not in the new structure.
    conn.execute(
        sa.text(
            """
            UPDATE categories
            SET is_active = FALSE, updated_at = now()
            WHERE parent_id = :men_id
              AND slug NOT IN :allowed_slugs
            """
        ),
        {"men_id": men_id, "allowed_slugs": tuple(allowed_men_slugs)},
    )

    # Deactivate any child categories under Men subcategories not in the new structure.
    conn.execute(
        sa.text(
            """
            UPDATE categories
            SET is_active = FALSE, updated_at = now()
            WHERE parent_id IN (
                SELECT id FROM categories
                WHERE parent_id = :men_id
                  AND slug NOT IN :allowed_slugs
            )
            """
        ),
        {"men_id": men_id, "allowed_slugs": tuple(allowed_men_slugs)},
    )


def downgrade():
    # No-op to avoid reactivating categories that may have been intentionally disabled.
    pass
