"""
Seed demo data for Shopsoma local development
Creates 1 vendor and 10 products with size and color variations
"""
import asyncio
import uuid
from datetime import datetime
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from passlib.context import CryptContext

from app.models.user import User
from app.models.vendor import Vendor, KYCStatus
from app.models.product import Product, ProductVariant, ProductImage, ProductStatus, ModerationStatus

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Color name to hex mapping
COLOR_HEX_MAP = {
    "White": "#FFFFFF",
    "Black": "#000000",
    "Navy": "#000080",
    "Gray": "#808080",
    "Blue": "#0000FF",
    "Light Blue": "#ADD8E6",
    "Dark Blue": "#00008B",
    "Pink": "#FFC0CB",
    "Red": "#FF0000",
    "Green": "#008000",
    "Brown": "#8B4513",
    "Khaki": "#F0E68C",
    "Olive": "#808000",
    "Burgundy": "#800020",
    "Charcoal": "#36454F",
}

# Database URL (async)
DATABASE_URL = "postgresql+asyncpg://shopsoma:shopsoma_dev_password@localhost:5432/shopsoma_db"

# Create async engine
engine = create_async_engine(DATABASE_URL, echo=True)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# Demo products data
PRODUCTS_DATA = [
    {
        "name": "Classic Cotton T-Shirt",
        "description": "Premium quality cotton t-shirt, perfect for everyday wear. Soft, breathable, and durable.",
        "category": "Clothing",
        "subcategory": "T-Shirts",
        "base_price": 5500.00,
        "colors": ["White", "Black", "Navy", "Gray"],
        "sizes": ["S", "M", "L", "XL"],
        "images": [
            "https://images.unsplash.com/photo-1521572163474-6864f9cf17ab?w=800",
            "https://images.unsplash.com/photo-1583743814966-8936f5b7be1a?w=800"
        ]
    },
    {
        "name": "Slim Fit Jeans",
        "description": "Modern slim fit jeans with stretch fabric for comfort. Classic 5-pocket design.",
        "category": "Clothing",
        "subcategory": "Jeans",
        "base_price": 12000.00,
        "colors": ["Blue", "Black", "Gray"],
        "sizes": ["28", "30", "32", "34", "36"],
        "images": [
            "https://images.unsplash.com/photo-1542272604-787c3835535d?w=800",
            "https://images.unsplash.com/photo-1541099649105-f69ad21f3246?w=800"
        ]
    },
    {
        "name": "Leather Sneakers",
        "description": "Premium leather sneakers with cushioned insole. Versatile style for casual or smart-casual occasions.",
        "category": "Footwear",
        "subcategory": "Sneakers",
        "base_price": 18500.00,
        "colors": ["White", "Black", "Brown"],
        "sizes": ["40", "41", "42", "43", "44", "45"],
        "images": [
            "https://images.unsplash.com/photo-1549298916-b41d501d3772?w=800",
            "https://images.unsplash.com/photo-1606107557195-0e29a4b5b4aa?w=800"
        ]
    },
    {
        "name": "Hooded Sweatshirt",
        "description": "Cozy fleece-lined hoodie with kangaroo pocket. Perfect for layering in cooler weather.",
        "category": "Clothing",
        "subcategory": "Hoodies",
        "base_price": 9500.00,
        "colors": ["Black", "Gray", "Navy", "Burgundy"],
        "sizes": ["S", "M", "L", "XL", "XXL"],
        "images": [
            "https://images.unsplash.com/photo-1556821840-3a63f95609a7?w=800",
            "https://images.unsplash.com/photo-1578587018452-892bacefd3f2?w=800"
        ]
    },
    {
        "name": "Cotton Dress Shirt",
        "description": "Crisp cotton dress shirt with button-down collar. Ideal for office or formal occasions.",
        "category": "Clothing",
        "subcategory": "Shirts",
        "base_price": 8500.00,
        "colors": ["White", "Light Blue", "Pink", "Black"],
        "sizes": ["S", "M", "L", "XL"],
        "images": [
            "https://images.unsplash.com/photo-1596755094514-f87e34085b2c?w=800",
            "https://images.unsplash.com/photo-1602810318383-e386cc2a3ccf?w=800"
        ]
    },
    {
        "name": "Casual Chino Pants",
        "description": "Versatile chino pants in stretch cotton twill. Perfect for smart-casual style.",
        "category": "Clothing",
        "subcategory": "Pants",
        "base_price": 10500.00,
        "colors": ["Khaki", "Navy", "Black", "Olive"],
        "sizes": ["28", "30", "32", "34", "36"],
        "images": [
            "https://images.unsplash.com/photo-1473966968600-fa801b869a1a?w=800",
            "https://images.unsplash.com/photo-1624378439575-d8705ad7ae80?w=800"
        ]
    },
    {
        "name": "Canvas Backpack",
        "description": "Durable canvas backpack with padded laptop compartment. Multiple pockets for organization.",
        "category": "Accessories",
        "subcategory": "Bags",
        "base_price": 14500.00,
        "colors": ["Black", "Gray", "Olive", "Navy"],
        "sizes": ["One Size"],
        "images": [
            "https://images.unsplash.com/photo-1553062407-98eeb64c6a62?w=800",
            "https://images.unsplash.com/photo-1622560480605-d83c853bc5c3?w=800"
        ]
    },
    {
        "name": "Summer Polo Shirt",
        "description": "Lightweight polo shirt with moisture-wicking fabric. Classic collar and button placket.",
        "category": "Clothing",
        "subcategory": "Polo Shirts",
        "base_price": 6500.00,
        "colors": ["White", "Navy", "Red", "Green"],
        "sizes": ["S", "M", "L", "XL"],
        "images": [
            "https://images.unsplash.com/photo-1607345366928-199ea26cfe3e?w=800",
            "https://images.unsplash.com/photo-1626497764746-6dc36546b388?w=800"
        ]
    },
    {
        "name": "Denim Jacket",
        "description": "Classic denim jacket with button closure. Timeless style that pairs with everything.",
        "category": "Clothing",
        "subcategory": "Jackets",
        "base_price": 15500.00,
        "colors": ["Light Blue", "Dark Blue", "Black"],
        "sizes": ["S", "M", "L", "XL"],
        "images": [
            "https://images.unsplash.com/photo-1551028719-00167b16eac5?w=800",
            "https://images.unsplash.com/photo-1576995853123-5a10305d93c0?w=800"
        ]
    },
    {
        "name": "Athletic Joggers",
        "description": "Comfortable joggers with elastic waistband and cuffs. Perfect for workouts or lounging.",
        "category": "Clothing",
        "subcategory": "Athletic Wear",
        "base_price": 7500.00,
        "colors": ["Black", "Gray", "Navy", "Charcoal"],
        "sizes": ["S", "M", "L", "XL", "XXL"],
        "images": [
            "https://images.unsplash.com/photo-1555274175-6cbf6f3b137b?w=800",
            "https://images.unsplash.com/photo-1552902865-b72c031ac5ea?w=800"
        ]
    }
]


async def create_demo_data():
    """Create demo vendor, products, variants, and images"""
    async with AsyncSessionLocal() as session:
        try:
            print("🚀 Starting demo data creation...")

            # 1. Create demo vendor user
            print("\n📦 Creating demo vendor user...")
            vendor_user = User(
                id=uuid.uuid4(),
                email="vendor@shopsoma.com",
                hashed_password=pwd_context.hash("Vendor123!"),
                full_name="Shopsoma Fashion Store",
                phone_number="+2348012345678",
                role="VENDOR",
                email_verified=True,
                is_active=True,
                is_guest_created=False,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            session.add(vendor_user)
            await session.flush()
            print(f"✅ Created vendor user: {vendor_user.email} (ID: {vendor_user.id})")

            # 2. Create vendor profile
            print("📦 Creating vendor profile...")
            vendor = Vendor(
                id=uuid.uuid4(),
                user_id=vendor_user.id,
                business_name="Shopsoma Fashion Store",
                business_description="Premium quality fashion and accessories for the modern shopper",
                business_address="123 Fashion Street, Lagos, Nigeria",
                business_phone="+2348012345678",
                kyc_status=KYCStatus.APPROVED,
                approved=True,
                approved_at=datetime.utcnow(),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            session.add(vendor)
            await session.flush()
            print(f"✅ Created vendor profile: {vendor.business_name} (ID: {vendor.id})")

            # 3. Create products with variants
            print(f"\n👕 Creating {len(PRODUCTS_DATA)} products with variations...")

            for idx, product_data in enumerate(PRODUCTS_DATA, 1):
                print(f"\n  [{idx}/{len(PRODUCTS_DATA)}] Creating: {product_data['name']}")

                # Create product
                product = Product(
                    id=uuid.uuid4(),
                    vendor_id=vendor.id,
                    title=product_data["name"],
                    description=product_data["description"],
                    base_price=product_data["base_price"],
                    status=ProductStatus.ACTIVE,
                    moderation_status=ModerationStatus.APPROVED,
                    is_featured=idx <= 3,  # Make first 3 products featured
                    total_stock=0,  # Will be calculated from variants
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                session.add(product)
                await session.flush()
                print(f"    ✓ Product created (ID: {product.id})")

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
                print(f"    ✓ Added {len(product_data['images'])} images")

                # Create variants for each color and size combination
                variant_count = 0
                for color in product_data["colors"]:
                    for size in product_data["sizes"]:
                        variant = ProductVariant(
                            id=uuid.uuid4(),
                            product_id=product.id,
                            sku=f"{product.title[:3].upper()}-{color[:3].upper()}-{size}".replace(" ", ""),
                            size=size,
                            color=color,
                            color_hex=COLOR_HEX_MAP.get(color),  # Map color name to hex
                            stock=20,  # 20 units per variant
                            price=product_data["base_price"],
                            is_available=True,
                            created_at=datetime.utcnow(),
                            updated_at=datetime.utcnow()
                        )
                        session.add(variant)
                        variant_count += 1

                await session.flush()
                print(f"    ✓ Created {variant_count} variants ({len(product_data['colors'])} colors × {len(product_data['sizes'])} sizes)")
                print(f"    ✓ Total inventory: {variant_count * 20} units")

            # Commit all changes
            await session.commit()

            print("\n" + "="*60)
            print("✨ Demo data creation completed successfully!")
            print("="*60)
            print(f"\n📊 Summary:")
            print(f"  • Vendor created: vendor@shopsoma.com (Password: Vendor123!)")
            print(f"  • Products created: {len(PRODUCTS_DATA)}")
            print(f"  • Total variants: {sum(len(p['colors']) * len(p['sizes']) for p in PRODUCTS_DATA)}")
            print(f"  • Total inventory: {sum(len(p['colors']) * len(p['sizes']) * 20 for p in PRODUCTS_DATA)} units")
            print(f"  • Featured products: 3")
            print("\n💡 You can now login as the vendor to manage these products!")

        except Exception as e:
            await session.rollback()
            print(f"\n❌ Error creating demo data: {e}")
            raise


async def main():
    """Main function"""
    try:
        await create_demo_data()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
