"""
Simple seeding endpoint - self-contained without external imports
"""
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from datetime import datetime
import uuid

from app.core.database import get_db
from app.models.product import Product, ProductVariant, ProductImage, ProductStatus
from app.models.user import User, UserRole
from app.core.security import get_password_hash

router = APIRouter(prefix="/seed", tags=["seed"])


@router.post("/initialize")
async def initialize_database(db: AsyncSession = Depends(get_db)):
    """
    Initialize database with demo products - self-contained version
    """
    try:
        # Check if already seeded
        result = await db.execute(select(Product))
        existing = result.scalars().first()

        if existing:
            return {
                "status": "already_seeded",
                "message": "Database already contains products. Use /seed/reset first if you want to re-seed."
            }

        # Create demo vendor
        vendor_id = uuid.uuid4()
        vendor_password = get_password_hash("password123")

        vendor = User(
            id=vendor_id,
            email="vendor@shopsoma.com",
            full_name="Demo Vendor",
            hashed_password=vendor_password,
            role=UserRole.VENDOR,
            email_verified=True,
            is_active=True
        )
        db.add(vendor)
        await db.flush()

        # Refresh to get the vendor with all attributes loaded
        await db.refresh(vendor)

        # Demo products configuration
        products_data = [
            {
                "title": "Classic Ankara Print Dress",
                "description": "Beautiful traditional Ankara print dress with modern cut",
                "price": 8900,
                "category": "Dresses",
                "images": [
                    "https://images.unsplash.com/photo-1515372039744-b8f02a3ae446?w=800&h=800&fit=crop"
                ],
                "colors": [
                    {"name": "Red Multi", "hex": "#DC143C"},
                    {"name": "Blue Multi", "hex": "#4169E1"},
                    {"name": "Green Multi", "hex": "#228B22"}
                ]
            },
            {
                "title": "African Print Maxi Skirt",
                "description": "Flowing maxi skirt with vibrant African patterns",
                "price": 6500,
                "category": "Skirts",
                "images": [
                    "https://images.unsplash.com/photo-1583496661160-fb5886a0aaaa?w=800&h=800&fit=crop"
                ],
                "colors": [
                    {"name": "Orange Mix", "hex": "#FF8C00"},
                    {"name": "Purple Mix", "hex": "#9370DB"},
                    {"name": "Teal Mix", "hex": "#008080"}
                ]
            },
            {
                "title": "Dashiki Shirt - Men",
                "description": "Traditional dashiki shirt with intricate embroidery",
                "price": 7500,
                "category": "Shirts",
                "images": [
                    "https://images.unsplash.com/photo-1490481651871-ab68de25d43d?w=800&h=800&fit=crop"
                ],
                "colors": [
                    {"name": "Navy", "hex": "#000080"},
                    {"name": "Maroon", "hex": "#800000"},
                    {"name": "Forest Green", "hex": "#228B22"}
                ]
            },
            {
                "title": "Kente Cloth Wrap",
                "description": "Authentic Kente cloth wrap from Ghana",
                "price": 12000,
                "category": "Accessories",
                "images": [
                    "https://images.unsplash.com/photo-1610652512264-b136a6caaa7f?w=800&h=800&fit=crop"
                ],
                "colors": [
                    {"name": "Gold & Black", "hex": "#FFD700"},
                    {"name": "Red & Gold", "hex": "#DC143C"},
                    {"name": "Blue & Gold", "hex": "#4169E1"}
                ]
            },
            {
                "title": "Buba and Sokoto Combo",
                "description": "Complete traditional men's outfit",
                "price": 15000,
                "category": "Sets",
                "images": [
                    "https://images.unsplash.com/photo-1503342217505-b0a15ec3261c?w=800&h=800&fit=crop"
                ],
                "colors": [
                    {"name": "White & Gold", "hex": "#FFFFFF"},
                    {"name": "Cream", "hex": "#FFFDD0"},
                    {"name": "Royal Blue", "hex": "#4169E1"}
                ]
            }
        ]

        created_products = []

        for prod_data in products_data:
            # Create product
            product = Product(
                id=uuid.uuid4(),
                title=prod_data["title"],
                description=prod_data["description"],
                base_price=prod_data["price"],
                category=prod_data["category"],
                vendor_id=vendor_id,
                status=ProductStatus.ACTIVE,
                featured=True
            )
            db.add(product)
            await db.flush()

            # Add images
            for img_url in prod_data["images"]:
                image = ProductImage(
                    id=uuid.uuid4(),
                    product_id=product.id,
                    image_url=img_url,
                    is_primary=True
                )
                db.add(image)

            # Add variants (3 colors × 3 sizes = 9 variants per product)
            for color in prod_data["colors"]:
                for size in ["L", "XL", "XXL"]:
                    variant = ProductVariant(
                        id=uuid.uuid4(),
                        product_id=product.id,
                        size=size,
                        color=color["name"],
                        color_hex=color["hex"],
                        price=prod_data["price"] + (100 if size == "XL" else 200 if size == "XXL" else 0),
                        stock=20,
                        sku=f"{prod_data['title'][:3].upper()}-{color['name'][:3].upper()}-{size}",
                        is_available=True
                    )
                    db.add(variant)

            created_products.append(product.title)

        await db.commit()

        return {
            "status": "success",
            "message": f"Created {len(created_products)} products with variants",
            "products": created_products
        }

    except Exception as e:
        await db.rollback()
        import traceback
        error_details = {
            "error": str(e),
            "type": type(e).__name__,
            "traceback": traceback.format_exc()
        }
        raise HTTPException(status_code=500, detail=f"Seeding failed: {str(e)}")


@router.delete("/reset")
async def reset_database(db: AsyncSession = Depends(get_db)):
    """Reset all products and variants"""
    try:
        await db.execute(text("DELETE FROM product_images"))
        await db.execute(text("DELETE FROM product_variants"))
        await db.execute(text("DELETE FROM products"))
        await db.commit()

        return {"status": "success", "message": "Database reset complete"}
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Reset failed: {str(e)}")
