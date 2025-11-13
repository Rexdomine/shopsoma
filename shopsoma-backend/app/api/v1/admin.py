"""
Admin API endpoints for database initialization and management
"""
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
import asyncio
import os

from app.core.database import get_db
from app.models.product import Product, ProductVariant, ProductImage, ProductStatus
from app.models.user import User

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/seed-database")
async def seed_database(db: AsyncSession = Depends(get_db)):
    """
    Initialize the database with demo products and data
    This endpoint runs all seeding scripts in sequence
    """
    try:
        # Import the seeding functions
        import sys
        sys.path.append('/opt/render/project/src/shopsoma-backend')

        from seed_products import seed_data as seed_base_products
        from activate_products import main as activate_products_main
        from update_products_with_variations import main as update_variations_main

        results = {
            "status": "success",
            "steps": []
        }

        # Step 1: Seed base products
        try:
            await seed_base_products()
            results["steps"].append({
                "step": "seed_products",
                "status": "success",
                "message": "Base products and vendors created"
            })
        except Exception as e:
            results["steps"].append({
                "step": "seed_products",
                "status": "error",
                "message": str(e)
            })

        # Step 2: Activate products with images
        try:
            await activate_products_main()
            results["steps"].append({
                "step": "activate_products",
                "status": "success",
                "message": "Products activated with images"
            })
        except Exception as e:
            results["steps"].append({
                "step": "activate_products",
                "status": "error",
                "message": str(e)
            })

        # Step 3: Add product variations
        try:
            await update_variations_main()
            results["steps"].append({
                "step": "update_variations",
                "status": "success",
                "message": "Product variations and size guides added"
            })
        except Exception as e:
            results["steps"].append({
                "step": "update_variations",
                "status": "error",
                "message": str(e)
            })

        # Get final counts
        product_count = await db.execute(select(func.count(Product.id)))
        variant_count = await db.execute(select(func.count(ProductVariant.id)))

        results["summary"] = {
            "total_products": product_count.scalar(),
            "total_variants": variant_count.scalar()
        }

        return results

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Seeding failed: {str(e)}")


@router.get("/database-status")
async def database_status(db: AsyncSession = Depends(get_db)):
    """
    Check the current state of the database
    """
    try:
        # Count products
        product_result = await db.execute(select(func.count(Product.id)))
        product_count = product_result.scalar()

        # Count active products
        active_result = await db.execute(
            select(func.count(Product.id)).where(Product.status == ProductStatus.ACTIVE)
        )
        active_count = active_result.scalar()

        # Count variants
        variant_result = await db.execute(select(func.count(ProductVariant.id)))
        variant_count = variant_result.scalar()

        # Count images
        image_result = await db.execute(select(func.count(ProductImage.id)))
        image_count = image_result.scalar()

        # Count users/vendors
        user_result = await db.execute(select(func.count(User.id)))
        user_count = user_result.scalar()

        vendor_result = await db.execute(
            select(func.count(User.id)).where(User.role == "vendor")
        )
        vendor_count = vendor_result.scalar()

        return {
            "status": "healthy",
            "database": {
                "products": {
                    "total": product_count,
                    "active": active_count
                },
                "variants": variant_count,
                "images": image_count,
                "users": {
                    "total": user_count,
                    "vendors": vendor_count
                }
            },
            "needs_seeding": product_count == 0
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database check failed: {str(e)}")


@router.delete("/reset-products")
async def reset_products(db: AsyncSession = Depends(get_db)):
    """
    Delete all products, variants, and images (for testing)
    """
    try:
        # Delete in correct order due to foreign keys
        await db.execute("DELETE FROM product_images")
        await db.execute("DELETE FROM product_variants")
        await db.execute("DELETE FROM products")
        await db.commit()

        return {
            "status": "success",
            "message": "All products, variants, and images deleted"
        }

    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Reset failed: {str(e)}")
