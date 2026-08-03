"""
Simple seeding endpoint - self-contained without external imports
"""
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from datetime import datetime
import uuid

from app.core.database import get_db
from app.models.product import Product, ProductVariant, ProductImage, ProductStatus, ModerationStatus
from app.models.user import User, UserRole
from app.models.vendor import Vendor, KYCStatus
from app.core.security import get_password_hash
from app.services.commission import DEFAULT_COMMISSION_RATE

router = APIRouter(prefix="/seed", tags=["seed"])


@router.get("/test-vendor")
async def test_vendor_creation(db: AsyncSession = Depends(get_db)):
    """Test vendor creation to debug the issue"""
    try:
        # Create User first
        user_id = uuid.uuid4()
        user_password = get_password_hash("password123")

        user = User(
            id=user_id,
            email="test@shopsoma.com",
            full_name="Test Vendor",
            hashed_password=user_password,
            role=UserRole.VENDOR,
            email_verified=True,
            is_active=True
        )
        db.add(user)
        await db.flush()

        # Then create Vendor entry
        vendor_id = uuid.uuid4()
        vendor = Vendor(
            id=vendor_id,
            user_id=user_id,
            business_name="Test Business",
            business_description="A test vendor business",
            kyc_status=KYCStatus.APPROVED,
            approved=True,
            commission_rate=DEFAULT_COMMISSION_RATE
        )
        db.add(vendor)
        await db.commit()

        return {"status": "success", "user_id": str(user_id), "vendor_id": str(vendor_id)}
    except Exception as e:
        await db.rollback()
        import traceback
        return {
            "status": "error",
            "error": str(e),
            "type": type(e).__name__,
            "traceback": traceback.format_exc()
        }


@router.get("/test-product")
async def test_product_creation(db: AsyncSession = Depends(get_db)):
    """Test product creation to debug the issue"""
    try:
        # Get a vendor first (from vendors table, not users)
        result = await db.execute(select(Vendor).limit(1))
        vendor = result.scalar_one_or_none()

        if not vendor:
            return {"status": "error", "message": "No vendor found. Run /test-vendor first."}

        # Create a test product
        product = Product(
            id=uuid.uuid4(),
            title="Test Product",
            description="Test description",
            base_price=1000,
            category_id=None,  # No category for test
            vendor_id=vendor.id,  # vendor.id from vendors table
            status="active",
            is_featured=True,
            moderation_status=ModerationStatus.APPROVED
        )

        db.add(product)
        await db.commit()

        return {"status": "success", "product_id": str(product.id), "vendor_id": str(vendor.id)}
    except Exception as e:
        await db.rollback()
        import traceback
        return {
            "status": "error",
            "error": str(e),
            "type": type(e).__name__,
            "traceback": traceback.format_exc()
        }


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

        # Create demo vendor user
        user_id = uuid.uuid4()
        vendor_password = get_password_hash("password123")

        user = User(
            id=user_id,
            email="vendor@shopsoma.com",
            full_name="Demo Vendor",
            hashed_password=vendor_password,
            role=UserRole.VENDOR,
            email_verified=True,
            is_active=True
        )
        db.add(user)
        await db.flush()

        # Create vendor business profile
        vendor_id = uuid.uuid4()
        vendor = Vendor(
            id=vendor_id,
            user_id=user_id,
            business_name="Shopsoma Demo Store",
            business_description="Premier African fashion marketplace featuring authentic designs",
            kyc_status=KYCStatus.APPROVED,
            approved=True,
            commission_rate=DEFAULT_COMMISSION_RATE
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
                ],
                "size_guide": {
                    "gender": "Women's",
                    "title": "Dress Size Guide",
                    "subtitle": "African Fashion Collection",
                    "rows": [
                        {"label": "L", "standard": "US 10-12", "measurement": "Bust: 36-38\" / Waist: 28-30\""},
                        {"label": "XL", "standard": "US 14-16", "measurement": "Bust: 40-42\" / Waist: 32-34\""},
                        {"label": "XXL", "standard": "US 18-20", "measurement": "Bust: 44-46\" / Waist: 36-38\""}
                    ]
                }
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
                ],
                "size_guide": {
                    "gender": "Women's",
                    "title": "Skirt Size Guide",
                    "subtitle": "African Fashion Collection",
                    "rows": [
                        {"label": "L", "standard": "US 10-12", "measurement": "Waist: 28-30\" / Hips: 38-40\""},
                        {"label": "XL", "standard": "US 14-16", "measurement": "Waist: 32-34\" / Hips: 42-44\""},
                        {"label": "XXL", "standard": "US 18-20", "measurement": "Waist: 36-38\" / Hips: 46-48\""}
                    ]
                }
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
                ],
                "size_guide": {
                    "gender": "Men's",
                    "title": "Shirt Size Guide",
                    "subtitle": "African Fashion Collection",
                    "rows": [
                        {"label": "L", "standard": "US 42-44", "measurement": "Chest: 42-44\" / Shoulder: 18\""},
                        {"label": "XL", "standard": "US 46-48", "measurement": "Chest: 46-48\" / Shoulder: 19\""},
                        {"label": "XXL", "standard": "US 50-52", "measurement": "Chest: 50-52\" / Shoulder: 20\""}
                    ]
                }
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
                ],
                "size_guide": {
                    "gender": "Unisex",
                    "title": "Wrap Size Guide",
                    "subtitle": "African Fashion Collection",
                    "rows": [
                        {"label": "L", "standard": "Standard", "measurement": "72\" x 44\" (183cm x 112cm)"},
                        {"label": "XL", "standard": "Large", "measurement": "82\" x 50\" (208cm x 127cm)"},
                        {"label": "XXL", "standard": "Extra Large", "measurement": "92\" x 56\" (234cm x 142cm)"}
                    ]
                }
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
                ],
                "size_guide": {
                    "gender": "Men's",
                    "title": "Traditional Set Size Guide",
                    "subtitle": "African Fashion Collection",
                    "rows": [
                        {"label": "L", "standard": "US 42-44", "measurement": "Chest: 42-44\" / Waist: 34-36\""},
                        {"label": "XL", "standard": "US 46-48", "measurement": "Chest: 46-48\" / Waist: 38-40\""},
                        {"label": "XXL", "standard": "US 50-52", "measurement": "Chest: 50-52\" / Waist: 42-44\""}
                    ]
                }
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
                category_id=None,  # No categories yet, nullable field
                vendor_id=vendor_id,
                status="active",
                is_featured=True,
                moderation_status=ModerationStatus.APPROVED,
                size_guide=prod_data.get("size_guide")
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
    """Reset all products, variants, and demo vendors"""
    try:
        # Delete in correct order due to foreign keys
        await db.execute(text("DELETE FROM product_images"))
        # This unrestricted destructive fixture reset has no bounded subject set;
        # the stock/payment coordinator intentionally fails closed after Lane 2A-4B.
        await db.execute(text("DELETE FROM product_variants"))
        await db.execute(text("DELETE FROM products"))
        await db.execute(text("DELETE FROM vendors WHERE business_name = 'Shopsoma Demo Store' OR business_name = 'Test Business'"))
        await db.execute(text("DELETE FROM users WHERE email IN ('vendor@shopsoma.com', 'test@shopsoma.com')"))
        await db.commit()

        return {"status": "success", "message": "Database reset complete - all demo data removed"}
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Reset failed: {str(e)}")


@router.post("/update-categories")
async def update_product_categories(db: AsyncSession = Depends(get_db)):
    """Update product descriptions to include category for search filtering"""
    try:
        result = await db.execute(select(Product))
        products = result.scalars().all()

        updated_count = 0
        updates = []

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

                if category and product.description:
                    # Only update if category not already in description
                    if category not in product.description:
                        product.description = f"{category} - {product.description}"
                        updated_count += 1
                        updates.append(f"{product.title} → {category}")

        await db.commit()

        return {
            "status": "success",
            "message": f"Updated {updated_count} product descriptions with categories",
            "updates": updates
        }
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Category update failed: {str(e)}")
