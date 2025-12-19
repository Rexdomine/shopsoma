#!/usr/bin/env python3
"""
Update "Queen of green" product with complete information
so we can test single product display on frontend
"""
import asyncio
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'shopsoma-backend'))

from sqlalchemy import select
from app.core.database import get_async_session
from app.models.product import Product


async def update_queen_of_green():
    """Update Queen of green product with complete information"""

    # Get database session
    async for db in get_async_session():
        try:
            # Find "Queen of green" product
            result = await db.execute(
                select(Product).where(Product.title == "Queen of green")
            )
            product = result.scalar_one_or_none()

            if not product:
                print("❌ Product 'Queen of green' not found")
                return

            print(f"✅ Found product: {product.title} (ID: {product.id})")
            print(f"   Current data:")
            print(f"   - care_instructions: {product.care_instructions}")
            print(f"   - fabric_composition: {product.fabric_composition}")
            print(f"   - product_type: {product.product_type}")
            print(f"   - category: {product.category_name}")

            # Update with complete information
            product.care_instructions = "Hand wash cold separately. Do not bleach. Lay flat to dry. Cool iron if needed. Do not dry clean."
            product.fabric_composition = "100% Premium Cotton. Ethically sourced and sustainably produced. Soft, breathable fabric with natural texture."
            product.made_to_order = True
            product.made_to_order_timeline = "Ships in 2-3 weeks"

            await db.commit()
            await db.refresh(product)

            print(f"\n✅ Product updated successfully!")
            print(f"   New data:")
            print(f"   - care_instructions: {product.care_instructions}")
            print(f"   - fabric_composition: {product.fabric_composition}")
            print(f"   - made_to_order: {product.made_to_order}")
            print(f"   - made_to_order_timeline: {product.made_to_order_timeline}")
            print(f"\n🎉 Reload the product detail page to see the changes!")

        except Exception as e:
            print(f"❌ Error: {e}")
            await db.rollback()
            raise
        finally:
            await db.close()
            break


if __name__ == "__main__":
    print("🔄 Updating 'Queen of green' product with complete information...\n")
    asyncio.run(update_queen_of_green())
