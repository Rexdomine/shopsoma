"""
Seed comprehensive demo products and vendors for Shopsoma local development.
Populates:
- Vendor account (vendor@shopsoma.com / Vendor123!)
- Approved active products (for homepage, featured collab, and storefront categories)
- Pending review products (for admin product management / moderation testing)
- Images, variants, colors, sizes, and shop-edits tags
"""
import asyncio
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.core.security import get_password_hash
from app.models.category import Category
from app.models.user import User, UserRole
from app.models.vendor import Vendor, KYCStatus
from app.models.product import (
    Product,
    ProductVariant,
    ProductImage,
    ProductStatus,
    ModerationStatus,
    ProductType,
)

COLOR_HEX_MAP = {
    "Emerald Green": "#0F766E",
    "Sahara Gold": "#D97706",
    "Onyx Black": "#111827",
    "Cream": "#FFFDD0",
    "Terracotta": "#E2725B",
    "Sage": "#9DC183",
    "Navy": "#000080",
    "Beige": "#F5F5DC",
    "Olive": "#808000",
    "Burgundy": "#800020",
    "White": "#FFFFFF",
    "Charcoal": "#36454F",
}

PRODUCTS_DATA = [
    {
        "title": "Artisan Linen Midi Dress",
        "description": "Hand-crafted midi dress in premium linen fabric. Features an elegant silhouette with breathable draping for all-day comfort.",
        "category_slug": "women-dresses",
        "base_price": Decimal("18500.00"),
        "is_featured": True,
        "moderation_status": ModerationStatus.APPROVED,
        "status": ProductStatus.ACTIVE,
        "shop_edit_slugs": ["shop-edits-occasion-wear-casual", "shop-edits-occasion-wear-evening"],
        "colors": ["Cream", "Terracotta", "Sage"],
        "sizes": ["S", "M", "L", "XL"],
        "images": [
            "https://images.unsplash.com/photo-1515372039744-b8f02a3ae446?w=1000&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1496747611176-843222e1e57c?w=1000&auto=format&fit=crop",
        ],
    },
    {
        "title": "Heritage Canvas Tote Bag",
        "description": "Premium structured canvas tote with genuine leather trims. Spacious interior with divided compartments for everyday luxury.",
        "category_slug": "accessories",
        "base_price": Decimal("12500.00"),
        "is_featured": True,
        "moderation_status": ModerationStatus.APPROVED,
        "status": ProductStatus.ACTIVE,
        "shop_edit_slugs": ["shop-edits-occasion-wear-workwear"],
        "colors": ["Beige", "Olive", "Charcoal"],
        "sizes": ["One Size"],
        "images": [
            "https://images.unsplash.com/photo-1544816155-12df9643f363?w=1000&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1590874103328-eac38a683ce7?w=1000&auto=format&fit=crop",
        ],
    },
    {
        "title": "Tailored Silk Blazer",
        "description": "Sharp contemporary tailored blazer crafted in raw silk blend. Features hand-finished lapels and horn buttons.",
        "category_slug": "men-tops",
        "base_price": Decimal("32000.00"),
        "is_featured": True,
        "moderation_status": ModerationStatus.APPROVED,
        "status": ProductStatus.ACTIVE,
        "shop_edit_slugs": ["shop-edits-occasion-wear-workwear", "shop-edits-occasion-wear-party"],
        "colors": ["Onyx Black", "Navy", "Emerald Green"],
        "sizes": ["M", "L", "XL"],
        "images": [
            "https://images.unsplash.com/photo-1507679799987-c73779587ccf?w=1000&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1593030761757-71fae45fa0e7?w=1000&auto=format&fit=crop",
        ],
    },
    {
        "title": "Classic Ankara Cotton T-Shirt",
        "description": "Heavyweight organic cotton jersey t-shirt with subtle Ankara fabric pocket detail. A timeless streetwear essential.",
        "category_slug": "men-tops-t-shirts",
        "base_price": Decimal("6500.00"),
        "is_featured": True,
        "moderation_status": ModerationStatus.APPROVED,
        "status": ProductStatus.ACTIVE,
        "shop_edit_slugs": ["shop-edits-occasion-wear-casual"],
        "colors": ["White", "Onyx Black", "Sage"],
        "sizes": ["S", "M", "L", "XL", "XXL"],
        "images": [
            "https://images.unsplash.com/photo-1521572267360-ee0c2909d518?w=1000&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1583743814966-8936f5b7be1a?w=1000&auto=format&fit=crop",
        ],
    },
    {
        "title": "African Print Maxi Skirt",
        "description": "High-waisted flowing maxi skirt in vibrant geometric African print with side pockets and a tiered ruffle hem.",
        "category_slug": "women-bottoms",
        "base_price": Decimal("14000.00"),
        "is_featured": False,
        "moderation_status": ModerationStatus.PENDING,
        "status": ProductStatus.ACTIVE,
        "shop_edit_slugs": ["shop-edits-occasion-wear-party"],
        "colors": ["Terracotta", "Sahara Gold", "Emerald Green"],
        "sizes": ["S", "M", "L", "XL"],
        "images": [
            "https://images.unsplash.com/photo-1583496661160-fb5886a0aaaa?w=1000&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1515886657613-9f3515b0c78f?w=1000&auto=format&fit=crop",
        ],
    },
    {
        "title": "Performance Activewear Compression Tee",
        "description": "Breathable moisture-wicking compression athletic shirt engineered for gym workouts and track training.",
        "category_slug": "men-activewear-tops",
        "base_price": Decimal("8500.00"),
        "is_featured": False,
        "moderation_status": ModerationStatus.PENDING,
        "status": ProductStatus.ACTIVE,
        "shop_edit_slugs": ["shop-edits-occasion-wear-casual"],
        "colors": ["Onyx Black", "Navy", "Charcoal"],
        "sizes": ["S", "M", "L", "XL"],
        "images": [
            "https://images.unsplash.com/photo-1581655353564-df123a1eb820?w=1000&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1506152983158-b4a74a01c721?w=1000&auto=format&fit=crop",
        ],
    },
    {
        "title": "Handcrafted Leather Chelsea Boots",
        "description": "Supple calfskin leather Chelsea boots with durable Goodyear welted crepe sole. Designed for timeless elegance.",
        "category_slug": "men-shoes",
        "base_price": Decimal("28000.00"),
        "is_featured": False,
        "moderation_status": ModerationStatus.PENDING,
        "status": ProductStatus.ACTIVE,
        "shop_edit_slugs": ["shop-edits-occasion-wear-evening"],
        "colors": ["Onyx Black", "Burgundy"],
        "sizes": ["41", "42", "43", "44", "45"],
        "images": [
            "https://images.unsplash.com/photo-1638247025967-b4e38f787b76?w=1000&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1549298916-b41d501d3772?w=1000&auto=format&fit=crop",
        ],
    },
    {
        "title": "Minimalist Silk Charmeuse Evening Gown",
        "description": "Fluid pure silk charmeuse evening gown with delicate cowl neckline and draped low back.",
        "category_slug": "women-dresses",
        "base_price": Decimal("45000.00"),
        "is_featured": True,
        "moderation_status": ModerationStatus.APPROVED,
        "status": ProductStatus.ACTIVE,
        "shop_edit_slugs": ["shop-edits-occasion-wear-evening", "shop-edits-occasion-wear-party"],
        "colors": ["Emerald Green", "Burgundy", "Onyx Black"],
        "sizes": ["XS", "S", "M", "L"],
        "images": [
            "https://images.unsplash.com/photo-1566174053879-31528523f8ae?w=1000&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1518611012118-696072aa579a?w=1000&auto=format&fit=crop",
        ],
    },
    {
        "title": "Relaxed Fit Pleated Trousers",
        "description": "Double-pleated wide leg trousers tailored in breathable tropical wool. Belt loops, side slash pockets, and clean cuffed hem.",
        "category_slug": "men-bottoms",
        "base_price": Decimal("16500.00"),
        "is_featured": False,
        "moderation_status": ModerationStatus.PENDING,
        "status": ProductStatus.ACTIVE,
        "shop_edit_slugs": ["shop-edits-occasion-wear-workwear"],
        "colors": ["Olive", "Charcoal", "Beige"],
        "sizes": ["30", "32", "34", "36"],
        "images": [
            "https://images.unsplash.com/photo-1473966968600-fa801b869a1a?w=1000&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1624378439575-d8705ad7ae80?w=1000&auto=format&fit=crop",
        ],
    },
]


async def seed_local_demo():
    async with AsyncSessionLocal() as session:
        print("[+] Seeding local database demo products and vendor...")

        # 1. Ensure demo vendor exists
        res = await session.execute(select(User).where(User.email == "vendor@shopsoma.com"))
        vendor_user = res.scalar_one_or_none()
        if not vendor_user:
            vendor_user = User(
                id=uuid.uuid4(),
                email="vendor@shopsoma.com",
                hashed_password=get_password_hash("Vendor123!"),
                full_name="Shopsoma Fashion Studio",
                role=UserRole.VENDOR,
                email_verified=True,
                is_active=True,
            )
            session.add(vendor_user)
            await session.flush()
            print("[OK] Created vendor user vendor@shopsoma.com")
        else:
            print("[OK] Vendor user vendor@shopsoma.com already exists")

        res_v = await session.execute(select(Vendor).where(Vendor.user_id == vendor_user.id))
        vendor = res_v.scalar_one_or_none()
        if not vendor:
            vendor = Vendor(
                id=uuid.uuid4(),
                user_id=vendor_user.id,
                business_name="Shopsoma Studio",
                business_description="Curated African luxury and contemporary fashion studio.",
                kyc_status=KYCStatus.APPROVED,
                approved=True,
                is_onboarding=False,
                store_active=True,
                store_deleted_at=None,
            )
            session.add(vendor)
            await session.flush()
            print("[OK] Created vendor profile Shopsoma Studio")
        else:
            print("[OK] Vendor profile already exists")

        # 2. Map existing categories by slug
        cats_res = await session.execute(select(Category))
        all_cats = cats_res.scalars().all()
        cat_map = {c.slug: c for c in all_cats}
        print(f"[OK] Found {len(all_cats)} categories in database")

        # 3. Create products
        created_count = 0
        for item in PRODUCTS_DATA:
            # Check if product with this title already exists
            existing_prod = await session.execute(
                select(Product).where(Product.title == item["title"])
            )
            if existing_prod.scalar_one_or_none():
                continue

            # Resolve category
            category = cat_map.get(item["category_slug"])
            if not category and "-" in item["category_slug"]:
                prefix = item["category_slug"].split("-")[0]
                category = cat_map.get(prefix)

            # Resolve shop edit categories
            shop_edit_cats = [cat_map[s] for s in item.get("shop_edit_slugs", []) if s in cat_map]

            prod_id = uuid.uuid4()
            prod = Product(
                id=prod_id,
                vendor_id=vendor.id,
                category_id=category.id if category else None,
                title=item["title"],
                description=item["description"],
                base_price=item["base_price"],
                compare_at_price=item["base_price"] + Decimal("2000.00"),
                currency="NGN",
                status=item["status"],
                is_featured=item["is_featured"],
                product_type=ProductType.SINGLE,
                moderation_status=item["moderation_status"],
                moderation_notes="Demo seeded product for testing",
                total_stock=0,
                shop_edit_categories=shop_edit_cats,
            )
            session.add(prod)
            await session.flush()

            # Add images
            for idx, img_url in enumerate(item["images"]):
                img = ProductImage(
                    id=uuid.uuid4(),
                    product_id=prod_id,
                    image_url=img_url,
                    thumbnail_url=img_url,
                    alt_text=f"{item['title']} view {idx + 1}",
                    display_order=idx,
                    is_primary=(idx == 0),
                )
                session.add(img)

            # Add variants
            variant_stock_sum = 0
            for col in item["colors"]:
                hex_val = COLOR_HEX_MAP.get(col, "#111827")
                for sz in item["sizes"]:
                    variant = ProductVariant(
                        id=uuid.uuid4(),
                        product_id=prod_id,
                        size=sz,
                        color=col,
                        color_hex=hex_val,
                        price=item["base_price"],
                        stock=15,
                        sku=f"{item['title'][:3].upper()}-{col[:3].upper()}-{sz}".replace(" ", ""),
                        is_available=True,
                    )
                    session.add(variant)
                    variant_stock_sum += 15

            prod.total_stock = variant_stock_sum
            created_count += 1
            print(f"  + Added product: {item['title']} ({item['moderation_status'].value}, featured={item['is_featured']})")

        await session.commit()
        print(f"\n[DONE] Successfully seeded {created_count} demo products into shopsoma_db!")


if __name__ == "__main__":
    asyncio.run(seed_local_demo())
