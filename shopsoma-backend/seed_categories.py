#!/usr/bin/env python3
"""
Seed categories: Primary categories (Men, Women, Beauty) and their subcategories
"""
import asyncio
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import AsyncSessionLocal
from app.models.category import Category


async def seed_categories():
    """Create primary categories and subcategories"""
    async with AsyncSessionLocal() as db:
        try:
            print("🌱 Seeding categories...")

            # Define category structure
            categories_data = [
                {
                    "name": "Men",
                    "slug": "men",
                    "description": "Men's fashion and accessories",
                    "display_order": 1,
                    "subcategories": [
                        {"name": "Men's Shirts", "slug": "men-shirts", "description": "Men's shirts and tops", "display_order": 1},
                        {"name": "Men's Pants", "slug": "men-pants", "description": "Men's pants and trousers", "display_order": 2},
                        {"name": "Men's Traditional Wear", "slug": "men-traditional", "description": "Men's traditional African clothing", "display_order": 3},
                        {"name": "Suits & Blazers", "slug": "men-suits", "description": "Men's formal wear", "display_order": 4},
                        {"name": "Men's Shoes", "slug": "men-shoes", "description": "Men's footwear", "display_order": 5},
                        {"name": "Men's Accessories", "slug": "men-accessories", "description": "Men's accessories", "display_order": 6},
                    ]
                },
                {
                    "name": "Women",
                    "slug": "women",
                    "description": "Women's fashion and accessories",
                    "display_order": 2,
                    "subcategories": [
                        {"name": "Women's Dresses", "slug": "women-dresses", "description": "Women's dresses", "display_order": 1},
                        {"name": "Women's Skirts", "slug": "women-skirts", "description": "Women's skirts", "display_order": 2},
                        {"name": "Tops & Blouses", "slug": "women-tops", "description": "Women's tops and blouses", "display_order": 3},
                        {"name": "Women's Pants", "slug": "women-pants", "description": "Women's pants and trousers", "display_order": 4},
                        {"name": "Women's Traditional Wear", "slug": "women-traditional", "description": "Women's traditional African clothing", "display_order": 5},
                        {"name": "Women's Gowns", "slug": "women-gowns", "description": "Women's gowns and evening wear", "display_order": 6},
                        {"name": "Women's Shoes", "slug": "women-shoes", "description": "Women's footwear", "display_order": 7},
                        {"name": "Bags & Accessories", "slug": "women-accessories", "description": "Women's bags and accessories", "display_order": 8},
                    ]
                },
                {
                    "name": "Beauty",
                    "slug": "beauty",
                    "description": "Beauty products and cosmetics",
                    "display_order": 3,
                    "subcategories": [
                        {"name": "Skincare", "slug": "beauty-skincare", "description": "Skincare products", "display_order": 1},
                        {"name": "Makeup", "slug": "beauty-makeup", "description": "Makeup and cosmetics", "display_order": 2},
                        {"name": "Haircare", "slug": "beauty-haircare", "description": "Hair care products", "display_order": 3},
                        {"name": "Fragrances", "slug": "beauty-fragrances", "description": "Perfumes and fragrances", "display_order": 4},
                        {"name": "Natural Products", "slug": "beauty-natural", "description": "Natural and organic beauty products", "display_order": 5},
                    ]
                },
            ]

            created_count = 0

            # Create primary categories and their subcategories
            for primary_data in categories_data:
                # Create primary category
                primary_category = Category(
                    id=uuid.uuid4(),
                    name=primary_data["name"],
                    slug=primary_data["slug"],
                    description=primary_data["description"],
                    display_order=primary_data["display_order"],
                    is_active=True,
                    parent_id=None
                )
                db.add(primary_category)
                await db.flush()  # Flush to get the ID

                print(f"✅ Created primary category: {primary_data['name']}")
                created_count += 1

                # Create subcategories
                for sub_data in primary_data["subcategories"]:
                    subcategory = Category(
                        id=uuid.uuid4(),
                        name=sub_data["name"],
                        slug=sub_data["slug"],
                        description=sub_data["description"],
                        display_order=sub_data["display_order"],
                        is_active=True,
                        parent_id=primary_category.id
                    )
                    db.add(subcategory)
                    print(f"  ↳ Created subcategory: {sub_data['name']}")
                    created_count += 1

            await db.commit()
            print(f"\n🎉 Successfully created {created_count} categories!")
            print("\nPrimary Categories:")
            print("  • Men (6 subcategories)")
            print("  • Women (8 subcategories)")
            print("  • Beauty (5 subcategories)")

        except Exception as e:
            await db.rollback()
            print(f"❌ Error seeding categories: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(seed_categories())
