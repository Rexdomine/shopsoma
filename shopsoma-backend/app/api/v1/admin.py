"""
Admin API endpoints for database initialization and management
"""
from typing import Optional, List
from uuid import UUID
from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, delete
import asyncio
import os

from app.core.database import get_db
from app.api.dependencies import get_current_admin
from app.models.product import Product, ProductVariant, ProductImage, ProductStatus
from app.models.user import User, UserRole
from app.schemas.auth import UserResponse, UserUpdate
from app.schemas.common import PaginatedResponse

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


# ===========================
# User Management Endpoints
# ===========================

# Response schemas for user management
class UserListItem(UserResponse):
    """User list item with additional fields"""
    created_at: Optional[str] = None
    last_login: Optional[str] = None


class UserListResponse(PaginatedResponse):
    """Paginated user list response"""
    items: List[UserListItem]


@router.get("/users", response_model=UserListResponse)
async def list_users(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    search: Optional[str] = Query(None, description="Search by name or email"),
    role: Optional[UserRole] = Query(None, description="Filter by role"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    List all users with pagination and filtering

    Requires admin role
    """
    # Build query
    query = select(User)

    # Apply filters
    filters = []

    if search:
        search_term = f"%{search}%"
        filters.append(
            or_(
                User.full_name.ilike(search_term),
                User.email.ilike(search_term)
            )
        )

    if role is not None:
        filters.append(User.role == role)

    if is_active is not None:
        filters.append(User.is_active == is_active)

    if filters:
        query = query.where(*filters)

    # Get total count
    count_query = select(func.count()).select_from(User)
    if filters:
        count_query = count_query.where(*filters)

    result = await db.execute(count_query)
    total = result.scalar()

    # Apply pagination
    query = query.order_by(User.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    users = result.scalars().all()

    # Calculate pagination info
    total_pages = (total + page_size - 1) // page_size

    return {
        "items": [
            {
                "id": str(user.id),
                "email": user.email,
                "full_name": user.full_name,
                "phone_number": user.phone_number,
                "role": user.role.value,
                "is_active": user.is_active,
                "email_verified": user.email_verified,
                "created_at": user.created_at.isoformat() if user.created_at else None,
                "last_login": None,  # User model doesn't have last_login field yet
            }
            for user in users
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }


@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: UUID,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Get detailed user information

    Requires admin role
    """
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return user


@router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: UUID,
    user_data: UserUpdate,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Update user information

    Requires admin role
    """
    # Get user
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Check if email is already taken
    if user_data.email and user_data.email != user.email:
        result = await db.execute(
            select(User).where(User.email == user_data.email)
        )
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=400,
                detail="Email already in use"
            )

    # Update fields
    if user_data.full_name is not None:
        user.full_name = user_data.full_name

    if user_data.email is not None:
        user.email = user_data.email

    if user_data.phone_number is not None:
        user.phone_number = user_data.phone_number

    await db.commit()
    await db.refresh(user)

    return user


@router.put("/users/{user_id}/status")
async def toggle_user_status(
    user_id: UUID,
    is_active: bool = Query(..., description="New active status"),
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Activate or deactivate a user account

    Requires admin role
    """
    # Get user
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Prevent admin from deactivating themselves
    if user.id == current_admin.id:
        raise HTTPException(
            status_code=400,
            detail="Cannot change your own status"
        )

    # Update status
    user.is_active = is_active

    await db.commit()
    await db.refresh(user)

    return {
        "message": f"User {'activated' if is_active else 'deactivated'} successfully",
        "user_id": str(user.id),
        "is_active": user.is_active
    }


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: UUID,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Delete a user account

    WARNING: This is a hard delete and cannot be undone.
    For production, consider using soft delete (is_active=False) instead.

    Requires admin role
    """
    # Get user
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Prevent admin from deleting themselves
    if user.id == current_admin.id:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete your own account"
        )

    # Manually delete related data in proper order to avoid foreign key constraint violations
    # Order matters: payments -> orders -> user
    from app.models.order import Order
    from app.models.payment import Payment

    # First, get all orders for this user
    orders_result = await db.execute(
        select(Order.id).where(Order.customer_id == user_id)
    )
    order_ids = [row[0] for row in orders_result.fetchall()]

    # Delete payments for these orders
    if order_ids:
        await db.execute(
            delete(Payment).where(Payment.order_id.in_(order_ids))
        )

    # Delete orders
    await db.execute(
        delete(Order).where(Order.customer_id == user_id)
    )

    # Delete user (cascade will handle addresses, cart_items, reviews, vendor, etc.)
    await db.delete(user)
    await db.commit()

    return {
        "message": "User deleted successfully",
        "user_id": str(user_id)
    }


@router.get("/stats")
async def get_admin_stats(
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Get admin dashboard statistics

    Requires admin role
    """
    # Total users
    total_users_result = await db.execute(
        select(func.count()).select_from(User)
    )
    total_users = total_users_result.scalar()

    # Active users
    active_users_result = await db.execute(
        select(func.count()).select_from(User).where(User.is_active == True)
    )
    active_users = active_users_result.scalar()

    # Users by role
    role_counts = {}
    for role in UserRole:
        result = await db.execute(
            select(func.count()).select_from(User).where(User.role == role)
        )
        role_counts[role.value] = result.scalar()

    # Verified emails
    verified_emails_result = await db.execute(
        select(func.count()).select_from(User).where(User.email_verified == True)
    )
    verified_emails = verified_emails_result.scalar()

    return {
        "total_users": total_users,
        "active_users": active_users,
        "inactive_users": total_users - active_users,
        "verified_emails": verified_emails,
        "role_breakdown": role_counts,
    }
