"""
Seed 4 featured demo products for Shopsoma homepage
Creates products with the demo SVG images
"""
import asyncio
import uuid
from datetime import datetime
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

from app.models.vendor import Vendor
from app.models.product import Product, ProductVariant, ProductImage, ProductStatus, ModerationStatus

# Color name to hex mapping
COLOR_HEX_MAP = {
    "Cream": "#FFFDD0",
    "Beige": "#F5F5DC",
    "Terracotta": "#E2725B",
    "Mustard": "#FFDB58",
    "Sage": "#9DC183",
    "Olive": "#808000",
    "Navy": "#000080",
    "Burgundy": "#800020",
    "Charcoal": "#36454F",
    "Caramel": "#C68E17",
}

# Database URL (async)
DATABASE_URL = "postgresql+asyncpg://shopsoma:shopsoma_dev_password@localhost:5432/shopsoma_db"

# Create async engine
engine = create_async_engine(DATABASE_URL, echo=True)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# Featured products data with SVG images
FEATURED_PRODUCTS = [
    {
        "name": "Artisan Linen Midi Dress",
        "description": "Hand-crafted midi dress in premium linen fabric. Features a relaxed silhouette with elegant draping and a timeless design perfect for both casual and formal occasions.",
        "category": "Clothing",
        "subcategory": "Dresses",
        "base_price": 18500.00,
        "colors": ["Cream", "Terracotta", "Sage"],
        "sizes": ["XS", "S", "M", "L", "XL"],
        "images": [
            "/images/demo-image-2.svg",
            "/images/demo-image-3.svg"
        ]
    },
    {
        "name": "Heritage Canvas Tote Bag",
        "description": "Premium canvas tote with leather accents. Spacious interior with multiple compartments, perfect for daily essentials. Sustainable and durable construction.",
        "category": "Accessories",
        "subcategory": "Bags",
        "base_price": 12500.00,
        "colors": ["Beige", "Olive", "Charcoal"],
        "sizes": ["One Size"],
        "images": [
            "/images/demo-image-3.svg",
            "/images/demo-image-4.svg"
        ]
    },
    {
        "name": "Contemporary Wool Blend Coat",
        "description": "Luxurious wool blend coat with modern tailoring. Features a relaxed fit, deep pockets, and statement collar. Perfect layering piece for the season.",
        "category": "Clothing",
        "subcategory": "Outerwear",
        "base_price": 32500.00,
        "colors": ["Caramel", "Navy", "Charcoal"],
        "sizes": ["S", "M", "L", "XL"],
        "images": [
            "/images/demo-image-4.svg",
            "/images/demo-image-5.svg"
        ]
    },
    {
        "name": "Minimalist Silk Scarf",
        "description": "Pure silk scarf with abstract print. Versatile accessory that can be worn multiple ways. Soft, lightweight, and adds a touch of elegance to any outfit.",
        "category": "Accessories",
        "subcategory": "Scarves",
        "base_price": 8500.00,
        "colors": ["Mustard", "Burgundy", "Sage"],
        "sizes": ["One Size"],
        "images": [
            "/images/demo-image-5.svg",
            "/images/demo-image-2.svg"
        ]
    }
]


async def create_featured_products():
    """Create 4 featured products for homepage display"""
    async with AsyncSessionLocal() as session:
        try:
            print("🚀 Starting featured products creation...\n")

            # Get existing vendor (should already exist from seed_demo_data.py)
            result = await session.execute(
                select(Vendor).where(Vendor.business_name == "Shopsoma Fashion Store").limit(1)
            )
            vendor = result.scalar_one_or_none()

            if not vendor:
                print("❌ No vendor found! Please run seed_demo_data.py first.")
                return

            print(f"✅ Found vendor: {vendor.business_name} (ID: {vendor.id})\n")

            # Create featured products
            print(f"👕 Creating {len(FEATURED_PRODUCTS)} featured products...\n")

            for idx, product_data in enumerate(FEATURED_PRODUCTS, 1):
                print(f"[{idx}/{len(FEATURED_PRODUCTS)}] Creating: {product_data['name']}")

                # Create product
                product = Product(
                    id=uuid.uuid4(),
                    vendor_id=vendor.id,
                    title=product_data["name"],
                    description=product_data["description"],
                    base_price=product_data["base_price"],
                    status=ProductStatus.ACTIVE,
                    moderation_status=ModerationStatus.APPROVED,
                    is_featured=True,  # All are featured products
                    total_stock=0,  # Will be calculated from variants
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                session.add(product)
                await session.flush()
                print(f"  ✓ Product created (ID: {product.id})")

                # Create product images
                for img_idx, image_url in enumerate(product_data["images"]):
                    image = ProductImage(
                        id=uuid.uuid4(),
                        product_id=product.id,
                        image_url=image_url,
                        alt_text=f"{product.title} - Image {img_idx + 1}",
                        display_order=img_idx,
                        is_primary=(img_idx == 0),
                        created_at=datetime.utcnow()
                    )
                    session.add(image)
                print(f"  ✓ Added {len(product_data['images'])} images")

                # Create variants for each color and size combination
                variant_count = 0
                total_stock = 0
                for color in product_data["colors"]:
                    for size in product_data["sizes"]:
                        stock = 15  # 15 units per variant
                        variant = ProductVariant(
                            id=uuid.uuid4(),
                            product_id=product.id,
                            sku=f"{product.title[:3].upper()}-{color[:3].upper()}-{size}".replace(" ", ""),
                            size=size,
                            color=color,
                            color_hex=COLOR_HEX_MAP.get(color),
                            stock=stock,
                            price=product_data["base_price"],
                            is_available=True,
                            created_at=datetime.utcnow(),
                            updated_at=datetime.utcnow()
                        )
                        session.add(variant)
                        variant_count += 1
                        total_stock += stock

                # Update product total_stock
                product.total_stock = total_stock

                await session.flush()
                print(f"  ✓ Created {variant_count} variants ({len(product_data['colors'])} colors × {len(product_data['sizes'])} sizes)")
                print(f"  ✓ Total inventory: {total_stock} units\n")

            # Commit all changes
            await session.commit()

            print("=" * 60)
            print("✨ Featured products creation completed successfully!")
            print("=" * 60)
            print(f"\n📊 Summary:")
            print(f"  • Featured products created: {len(FEATURED_PRODUCTS)}")
            print(f"  • All products set as featured: ✓")
            print(f"  • Using demo SVG images: ✓")
            print(f"  • Total variants: {sum(len(p['colors']) * len(p['sizes']) for p in FEATURED_PRODUCTS)}")
            print(f"  • Total inventory: {sum(len(p['colors']) * len(p['sizes']) * 15 for p in FEATURED_PRODUCTS)} units")
            print("\n💡 These products will now appear on the homepage!")

        except Exception as e:
            await session.rollback()
            print(f"\n❌ Error creating featured products: {e}")
            raise


async def main():
    """Main function"""
    try:
        await create_featured_products()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
