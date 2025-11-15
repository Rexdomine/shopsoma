#!/usr/bin/env python3
"""
Update Product Categories Based on Size Guide Gender

This script adds a 'category' field to products based on their size_guide gender.
This allows the frontend search to filter by Women/Men.
"""

import asyncio
from app.core.database import AsyncSessionLocal
from app.models.product import Product
from sqlalchemy import select, update


async def update_categories():
    """Update product categories based on size guide gender"""
    async with AsyncSessionLocal() as db:
        try:
            # Fetch all products
            result = await db.execute(select(Product))
            products = result.scalars().all()

            print(f"Found {len(products)} products\n")
            print("="*80)

            updated_count = 0

            for product in products:
                size_guide = product.size_guide
                if size_guide and isinstance(size_guide, dict):
                    gender = size_guide.get("gender", "")

                    # Map gender to category
                    category = None
                    if "women" in gender.lower():
                        category = "Women"
                    elif "men" in gender.lower():
                        category = "Men"
                    elif "unisex" in gender.lower():
                        category = "Unisex"

                    if category:
                        # Update description to include category for search
                        if product.description:
                            if category not in product.description:
                                product.description = f"{category} - {product.description}"
                        else:
                            product.description = f"{category} product"

                        updated_count += 1
                        print(f"✓ {product.title}")
                        print(f"  Category: {category}")
                        print(f"  Updated description: {product.description[:80]}...")
                        print("-"*80)

            await db.commit()

            print("\n" + "="*80)
            print(f"✓ Updated {updated_count} products")
            print("="*80)

        except Exception as e:
            await db.rollback()
            print(f"✗ Error: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(update_categories())
