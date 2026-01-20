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
                        {
                            "name": "Tops",
                            "slug": "men-tops",
                            "description": "Men's tops",
                            "display_order": 1,
                            "children": [
                                {"name": "T-Shirts", "slug": "men-tops-t-shirts", "description": "Men's t-shirts", "display_order": 1},
                                {"name": "Shirts", "slug": "men-tops-shirts", "description": "Men's shirts", "display_order": 2},
                            ],
                        },
                        {
                            "name": "Bottoms",
                            "slug": "men-bottoms",
                            "description": "Men's bottoms",
                            "display_order": 2,
                            "children": [
                                {"name": "Jeans", "slug": "men-bottoms-jeans", "description": "Men's jeans", "display_order": 1},
                                {"name": "Trousers", "slug": "men-bottoms-trousers", "description": "Men's trousers", "display_order": 2},
                                {"name": "Shorts", "slug": "men-bottoms-shorts", "description": "Men's shorts", "display_order": 3},
                            ],
                        },
                        {
                            "name": "Activewear",
                            "slug": "men-activewear",
                            "description": "Men's activewear",
                            "display_order": 3,
                            "children": [
                                {"name": "Activewear Tops", "slug": "men-activewear-tops", "description": "Men's activewear tops", "display_order": 1},
                                {"name": "Activewear Bottoms", "slug": "men-activewear-bottoms", "description": "Men's activewear bottoms", "display_order": 2},
                            ],
                        },
                        {
                            "name": "Shoes",
                            "slug": "men-shoes",
                            "description": "Men's footwear",
                            "display_order": 4,
                            "children": [
                                {"name": "Casual Shoes", "slug": "men-shoes-casual", "description": "Men's casual shoes", "display_order": 1},
                                {"name": "Formal Shoes", "slug": "men-shoes-formal", "description": "Men's formal shoes", "display_order": 2},
                            ],
                        },
                        {
                            "name": "Accessories",
                            "slug": "men-accessories",
                            "description": "Men's accessories",
                            "display_order": 5,
                            "children": [
                                {"name": "Watches/Jewellery", "slug": "men-accessories-watches-jewellery", "description": "Watches and jewellery", "display_order": 1},
                                {"name": "Wallets", "slug": "men-accessories-wallets", "description": "Wallets", "display_order": 2},
                                {"name": "Belts", "slug": "men-accessories-belts", "description": "Belts", "display_order": 3},
                                {"name": "Sunglasses", "slug": "men-accessories-sunglasses", "description": "Sunglasses", "display_order": 4},
                                {"name": "Caps/Hats", "slug": "men-accessories-caps-hats", "description": "Caps and hats", "display_order": 5},
                            ],
                        },
                        {
                            "name": "Outerwear",
                            "slug": "men-outerwear",
                            "description": "Men's outerwear",
                            "display_order": 6,
                            "children": [
                                {"name": "Hoodies", "slug": "men-outerwear-hoodies", "description": "Hoodies", "display_order": 1},
                            ],
                        },
                    ]
                },
                {
                    "name": "Women",
                    "slug": "women",
                    "description": "Women's fashion and accessories",
                    "display_order": 2,
                    "subcategories": [
                        {
                            "name": "Women's Tops",
                            "slug": "women-tops",
                            "description": "Women's tops",
                            "display_order": 1,
                            "children": [
                                {"name": "Women's T-Shirts", "slug": "women-tops-t-shirts", "description": "Women's t-shirts", "display_order": 1},
                                {"name": "Women's Shirts", "slug": "women-tops-shirts", "description": "Women's shirts", "display_order": 2},
                                {"name": "Women's Blouses", "slug": "women-tops-blouses", "description": "Women's blouses", "display_order": 3},
                            ],
                        },
                        {
                            "name": "Women's Dresses",
                            "slug": "women-dresses",
                            "description": "Women's dresses",
                            "display_order": 2,
                            "children": [
                                {"name": "Casual Dresses", "slug": "women-dresses-casual", "description": "Casual dresses", "display_order": 1},
                                {"name": "Party Dresses", "slug": "women-dresses-party", "description": "Party dresses", "display_order": 2},
                                {"name": "Formal Dresses", "slug": "women-dresses-formal", "description": "Formal dresses", "display_order": 3},
                            ],
                        },
                        {
                            "name": "Women's Bottoms",
                            "slug": "women-bottoms",
                            "description": "Women's bottoms",
                            "display_order": 3,
                            "children": [
                                {"name": "Women's Jeans", "slug": "women-bottoms-jeans", "description": "Women's jeans", "display_order": 1},
                                {"name": "Women's Skirts", "slug": "women-bottoms-skirts", "description": "Women's skirts", "display_order": 2},
                                {"name": "Women's Trousers", "slug": "women-bottoms-trousers", "description": "Women's trousers", "display_order": 3},
                            ],
                        },
                        {
                            "name": "Women's Accessories",
                            "slug": "women-accessories",
                            "description": "Women's accessories",
                            "display_order": 4,
                            "children": [
                                {"name": "Women's Jewellery", "slug": "women-accessories-jewellery", "description": "Jewellery", "display_order": 1},
                                {"name": "Women's Bracelets", "slug": "women-accessories-bracelets", "description": "Bracelets", "display_order": 2},
                                {"name": "Women's Earrings", "slug": "women-accessories-earrings", "description": "Earrings", "display_order": 3},
                                {"name": "Women's Necklace", "slug": "women-accessories-necklace", "description": "Necklaces", "display_order": 4},
                                {"name": "Women's Rings", "slug": "women-accessories-rings", "description": "Rings", "display_order": 5},
                                {"name": "Women's Watches", "slug": "women-accessories-watches", "description": "Watches", "display_order": 6},
                                {"name": "Women's Anklets", "slug": "women-accessories-anklets", "description": "Anklets", "display_order": 7},
                                {"name": "Women's Body Jewellery", "slug": "women-accessories-body-jewellery", "description": "Body jewellery", "display_order": 8},
                                {"name": "Women's Brooches", "slug": "women-accessories-brooches", "description": "Brooches", "display_order": 9},
                                {"name": "Women's Bags", "slug": "women-accessories-bags", "description": "Bags", "display_order": 10},
                                {"name": "Women's Belts", "slug": "women-accessories-belts", "description": "Belts", "display_order": 11},
                                {"name": "Women's Sunglasses", "slug": "women-accessories-sunglasses", "description": "Sunglasses", "display_order": 12},
                            ],
                        },
                        {
                            "name": "Women's Shoes",
                            "slug": "women-shoes",
                            "description": "Women's footwear",
                            "display_order": 5,
                            "children": [
                                {"name": "Women's Flats", "slug": "women-shoes-flats", "description": "Flats", "display_order": 1},
                                {"name": "Women's Heels", "slug": "women-shoes-heels", "description": "Heels", "display_order": 2},
                            ],
                        },
                        {
                            "name": "Women's Activewear",
                            "slug": "women-activewear",
                            "description": "Women's activewear",
                            "display_order": 6,
                            "children": [
                                {"name": "Women's Activewear Tops", "slug": "women-activewear-tops", "description": "Activewear tops", "display_order": 1},
                                {"name": "Women's Activewear Bottoms", "slug": "women-activewear-bottoms", "description": "Activewear bottoms", "display_order": 2},
                            ],
                        },
                        {
                            "name": "Women's Outerwear",
                            "slug": "women-outerwear",
                            "description": "Women's outerwear",
                            "display_order": 7,
                            "children": [
                                {"name": "Women's Jackets", "slug": "women-outerwear-jackets", "description": "Jackets", "display_order": 1},
                                {"name": "Women's Kaftan", "slug": "women-outerwear-kaftan", "description": "Kaftan", "display_order": 2},
                                {"name": "Women's Kimonos", "slug": "women-outerwear-kimonos", "description": "Kimonos", "display_order": 3},
                                {"name": "Women's Ponchos", "slug": "women-outerwear-ponchos", "description": "Ponchos", "display_order": 4},
                                {"name": "Women's Hoodies/Sweatshirts", "slug": "women-outerwear-hoodies-sweatshirts", "description": "Hoodies and sweatshirts", "display_order": 5},
                            ],
                        },
                        {
                            "name": "Women's Swimwear",
                            "slug": "women-swimwear",
                            "description": "Women's swimwear",
                            "display_order": 8,
                        },
                        {
                            "name": "Women's Lingerie/Pyjamas",
                            "slug": "women-lingerie-pyjamas",
                            "description": "Women's lingerie and pyjamas",
                            "display_order": 9,
                        },
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
                {
                    "name": "Shop Edits",
                    "slug": "shop-edits",
                    "description": "Curated edits and seasonal picks",
                    "display_order": 4,
                    "subcategories": [
                        {
                            "name": "Seasonal (Summer / Winter)",
                            "slug": "shop-edits-seasonal",
                            "description": "Seasonal selections",
                            "display_order": 1,
                        },
                        {
                            "name": "Occasion Wear",
                            "slug": "shop-edits-occasion-wear",
                            "description": "Occasion wear edits",
                            "display_order": 2,
                            "children": [
                                {"name": "Casual", "slug": "shop-edits-occasion-wear-casual", "description": "Casual edits", "display_order": 1},
                                {"name": "Workwear", "slug": "shop-edits-occasion-wear-workwear", "description": "Workwear edits", "display_order": 2},
                                {"name": "Party", "slug": "shop-edits-occasion-wear-party", "description": "Party edits", "display_order": 3},
                            ],
                        },
                        {
                            "name": "Designer Picks",
                            "slug": "shop-edits-designer-picks",
                            "description": "Designer picks",
                            "display_order": 3,
                        },
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

                    for child_data in sub_data.get("children", []):
                        child_category = Category(
                            id=uuid.uuid4(),
                            name=child_data["name"],
                            slug=child_data["slug"],
                            description=child_data["description"],
                            display_order=child_data["display_order"],
                            is_active=True,
                            parent_id=subcategory.id
                        )
                        db.add(child_category)
                        print(f"    ↳ Created child category: {child_data['name']}")
                        created_count += 1

            await db.commit()
            print(f"\n🎉 Successfully created {created_count} categories!")
            print("\nPrimary Categories:")
            print("  • Men (7 subcategories)")
            print("  • Women (9 subcategories)")
            print("  • Beauty (5 subcategories)")

        except Exception as e:
            await db.rollback()
            print(f"❌ Error seeding categories: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(seed_categories())
