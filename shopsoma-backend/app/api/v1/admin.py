"""
Admin API endpoints for database initialization and management
"""
from typing import Optional, List
from uuid import UUID
from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, delete
from sqlalchemy.orm import selectinload
from datetime import datetime
from decimal import Decimal
import asyncio
import os

from app.core.database import get_db
from app.api.dependencies import get_current_admin
from app.models.product import Product, ProductVariant, ProductImage, ProductStatus, ModerationStatus
from app.models.user import User, UserRole
from app.models.vendor import Vendor, KYCStatus
from app.models.vendor_application import VendorApplication
from app.schemas.auth import UserResponse, UserUpdate
from app.schemas.common import PaginatedResponse
from app.schemas.product import ProductApprovalRequest, ProductRejectionRequest, ProductFeatureUpdate

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
    # Order matters: payments -> orders -> vendor applications -> user
    from app.models.order import Order
    from app.models.payment import Payment
    from app.models.returns import Return
    from app.models.vendor_application import VendorApplication
    from app.models.vendor_pickup import VendorPickup

    # First, get all orders for this user
    orders_result = await db.execute(
        select(Order.id).where(Order.customer_id == user_id)
    )
    order_ids = [row[0] for row in orders_result.fetchall()]

    # Delete vendor pickups tied to these orders (FKs are RESTRICT)
    if order_ids:
        await db.execute(
            delete(VendorPickup).where(VendorPickup.order_id.in_(order_ids))
        )

    # Delete returns tied to these orders (FKs are RESTRICT)
    if order_ids:
        await db.execute(
            delete(Return).where(Return.order_id.in_(order_ids))
        )

    # Delete returns tied to this customer (FKs are RESTRICT)
    await db.execute(
        delete(Return).where(Return.customer_id == user_id)
    )

    # Delete payments for these orders
    if order_ids:
        await db.execute(
            delete(Payment).where(Payment.order_id.in_(order_ids))
        )

    # Delete orders
    await db.execute(
        delete(Order).where(Order.customer_id == user_id)
    )

    # Delete vendor application if this was a vendor (matched by email)
    await db.execute(
        delete(VendorApplication).where(VendorApplication.email == user.email)
    )

    # Delete user (cascade will handle addresses, cart_items, reviews, vendor, etc.)
    await db.delete(user)
    await db.commit()

    return {
        "message": "User deleted successfully",
        "user_id": str(user_id)
    }


@router.post("/users/{user_id}/reset-password")
async def reset_user_password(
    user_id: UUID,
    request: dict,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Reset a user's password (admin only)

    Request body:
    {
        "new_password": "newpassword123"
    }
    """
    # Get user
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Prevent admin from resetting their own password this way
    if user.id == current_admin.id:
        raise HTTPException(
            status_code=400,
            detail="Cannot reset your own password. Use the change password feature instead."
        )

    # Validate new password
    new_password = request.get("new_password", "").strip()
    if not new_password:
        raise HTTPException(
            status_code=400,
            detail="New password is required"
        )

    if len(new_password) < 8:
        raise HTTPException(
            status_code=400,
            detail="Password must be at least 8 characters long"
        )

    # Update password
    from app.core.security import get_password_hash
    user.hashed_password = get_password_hash(new_password)
    await db.commit()

    return {
        "message": "Password reset successfully",
        "user_id": str(user_id),
        "email": user.email
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

# ==================== VENDOR MANAGEMENT ENDPOINTS ====================

@router.get("/vendors")
async def list_vendors(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    search: Optional[str] = Query(None, description="Search by business name or email"),
    approved: Optional[bool] = Query(None, description="Filter by approval status"),
    kyc_status: Optional[KYCStatus] = Query(None, description="Filter by KYC status"),
    is_active: Optional[bool] = Query(None, description="Filter by account active status"),
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    List all vendors with pagination and filtering
    
    Requires admin role
    """
    # Build query with join to User
    query = select(Vendor, User).join(User, Vendor.user_id == User.id)
    
    # Apply filters
    filters = []
    
    if search:
        search_term = f"%{search}%"
        filters.append(
            or_(
                Vendor.business_name.ilike(search_term),
                User.email.ilike(search_term),
                User.full_name.ilike(search_term)
            )
        )
    
    if approved is not None:
        filters.append(Vendor.approved == approved)
    
    if kyc_status is not None:
        filters.append(Vendor.kyc_status == kyc_status)
    
    if is_active is not None:
        filters.append(User.is_active == is_active)
    
    if filters:
        query = query.where(*filters)
    
    # Get total count
    count_query = select(func.count()).select_from(Vendor).join(User, Vendor.user_id == User.id)
    if filters:
        count_query = count_query.where(*filters)
    
    result = await db.execute(count_query)
    total = result.scalar()
    
    # Apply pagination
    query = query.order_by(Vendor.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    
    result = await db.execute(query)
    vendors_with_users = result.all()
    
    # Calculate pagination info
    total_pages = (total + page_size - 1) // page_size
    
    return {
        "items": [
            {
                "id": str(vendor.id),
                "user_id": str(vendor.user_id),
                "business_name": vendor.business_name,
                "business_description": vendor.business_description,
                "business_address": vendor.business_address,
                "business_phone": vendor.business_phone,
                "email": user.email,
                "full_name": user.full_name,
                "approved": vendor.approved,
                "approved_at": vendor.approved_at.isoformat() if vendor.approved_at else None,
                "kyc_status": vendor.kyc_status.value if vendor.kyc_status else None,
                "kyc_submitted_at": vendor.kyc_submitted_at.isoformat() if vendor.kyc_submitted_at else None,
                "commission_rate": float(vendor.commission_rate) if vendor.commission_rate else 0.0,
                "is_active": user.is_active,
                "is_onboarding": vendor.is_onboarding,
                "brand_info_completed": vendor.brand_info_completed,
                "payout_info_completed": vendor.payout_info_completed,
                "total_products": vendor.total_products or 0,
                "total_orders": vendor.total_orders or 0,
                "total_revenue": float(vendor.total_revenue) if vendor.total_revenue else 0.0,
                "created_at": vendor.created_at.isoformat() if vendor.created_at else None,
                "store_active": vendor.store_active,
                "store_paused_at": vendor.store_paused_at.isoformat() if vendor.store_paused_at else None,
                "store_deleted_at": vendor.store_deleted_at.isoformat() if vendor.store_deleted_at else None,
            }
            for vendor, user in vendors_with_users
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }


@router.get("/vendors/{vendor_id}")
async def get_vendor_details(
    vendor_id: UUID,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Get detailed vendor information including user account and metrics
    
    Requires admin role
    """
    # Get vendor with user
    result = await db.execute(
        select(Vendor, User).join(User, Vendor.user_id == User.id).where(Vendor.id == vendor_id)
    )
    vendor_with_user = result.first()
    
    if not vendor_with_user:
        raise HTTPException(status_code=404, detail="Vendor not found")
    
    vendor, user = vendor_with_user
    
    # Get product count
    product_count_result = await db.execute(
        select(func.count()).select_from(Product).where(Product.vendor_id == vendor_id)
    )
    product_count = product_count_result.scalar()
    
    return {
        "id": str(vendor.id),
        "user_id": str(vendor.user_id),
        "user": {
            "email": user.email,
            "full_name": user.full_name,
            "phone_number": user.phone_number,
            "is_active": user.is_active,
            "email_verified": user.email_verified,
            "created_at": user.created_at.isoformat() if user.created_at else None,
        },
        "business_name": vendor.business_name,
        "business_description": vendor.business_description,
        "business_address": vendor.business_address,
        "business_phone": vendor.business_phone,
        "approved": vendor.approved,
        "approved_at": vendor.approved_at.isoformat() if vendor.approved_at else None,
        "approved_by": str(vendor.approved_by) if vendor.approved_by else None,
        "kyc_status": vendor.kyc_status.value if vendor.kyc_status else None,
        "kyc_document_type": vendor.kyc_document_type,
        "kyc_document_url": vendor.kyc_document_url,
        "kyc_submitted_at": vendor.kyc_submitted_at.isoformat() if vendor.kyc_submitted_at else None,
        "kyc_reviewed_at": vendor.kyc_reviewed_at.isoformat() if vendor.kyc_reviewed_at else None,
        "bank_name": vendor.bank_name,
        "bank_account_number": vendor.bank_account_number,
        "bank_account_name": vendor.bank_account_name,
        "commission_rate": float(vendor.commission_rate) if vendor.commission_rate else 0.0,
        "is_onboarding": vendor.is_onboarding,
        "brand_info_completed": vendor.brand_info_completed,
        "payout_info_completed": vendor.payout_info_completed,
        "onboarding_completed_at": vendor.onboarding_completed_at.isoformat() if vendor.onboarding_completed_at else None,
        "total_products": product_count,
        "total_orders": vendor.total_orders or 0,
        "total_revenue": float(vendor.total_revenue) if vendor.total_revenue else 0.0,
        "created_at": vendor.created_at.isoformat() if vendor.created_at else None,
        "updated_at": vendor.updated_at.isoformat() if vendor.updated_at else None,
    }


@router.put("/vendors/{vendor_id}/commission")
async def update_vendor_commission(
    vendor_id: UUID,
    commission_rate: float = Query(..., ge=0, le=100, description="Commission rate percentage (0-100)"),
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Update vendor commission rate
    
    Requires admin role
    """
    result = await db.execute(
        select(Vendor).where(Vendor.id == vendor_id)
    )
    vendor = result.scalar_one_or_none()
    
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")
    
    vendor.commission_rate = commission_rate
    
    await db.commit()
    await db.refresh(vendor)
    
    return {
        "message": "Commission rate updated successfully",
        "vendor_id": str(vendor.id),
        "commission_rate": float(vendor.commission_rate)
    }


@router.put("/vendors/{vendor_id}/approve")
async def approve_vendor(
    vendor_id: UUID,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Approve a vendor account
    
    Requires admin role
    """
    from app.services.email_service import email_service

    # Get vendor with user
    result = await db.execute(
        select(Vendor, User).join(User, Vendor.user_id == User.id).where(Vendor.id == vendor_id)
    )
    vendor_with_user = result.first()

    if not vendor_with_user:
        raise HTTPException(status_code=404, detail="Vendor not found")

    vendor, user = vendor_with_user

    # Check if already approved
    if vendor.approved:
        raise HTTPException(status_code=400, detail="Vendor is already approved")

    # Update vendor status
    vendor.approved = True
    vendor.approved_at = func.now()
    await db.commit()

    # Send approval email
    try:
        await email_service.send_vendor_approved_email(
            email=user.email,
            vendor_name=user.full_name or vendor.business_name,
            business_name=vendor.business_name
        )
    except Exception as e:
        # Log error but don't fail approval
        print(f"Error sending approval email: {e}")

    return {
        "message": "Vendor approved successfully",
        "vendor_id": str(vendor_id)
    }


@router.put("/vendors/{vendor_id}/kyc/approve")
async def approve_vendor_kyc(
    vendor_id: UUID,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Approve vendor KYC
    
    Requires admin role
    """
    from app.services.email_service import email_service

    # Get vendor
    result = await db.execute(
        select(Vendor, User).join(User, Vendor.user_id == User.id).where(Vendor.id == vendor_id)
    )
    vendor_with_user = result.first()

    if not vendor_with_user:
        raise HTTPException(status_code=404, detail="Vendor not found")

    vendor, user = vendor_with_user

    # Update KYC status
    vendor.kyc_status = KYCStatus.APPROVED
    vendor.kyc_reviewed_at = func.now()
    vendor.kyc_reviewer_id = current_admin.id
    await db.commit()

    # Send KYC approval email
    try:
        await email_service.send_vendor_kyc_approved_email(
            email=user.email,
            vendor_name=user.full_name or vendor.business_name,
            business_name=vendor.business_name
        )
    except Exception as e:
        print(f"Error sending KYC approval email: {e}")

    return {
        "message": "Vendor KYC approved successfully",
        "vendor_id": str(vendor_id),
        "kyc_status": vendor.kyc_status.value,
        "kyc_reviewed_at": vendor.kyc_reviewed_at.isoformat(),
    }


@router.put("/vendors/{vendor_id}/kyc/reject")
async def reject_vendor_kyc(
    vendor_id: UUID,
    reason: str = Query(..., description="Reason for rejection"),
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Reject vendor KYC
    
    Requires admin role
    """
    from app.services.email_service import email_service

    # Get vendor
    result = await db.execute(
        select(Vendor, User).join(User, Vendor.user_id == User.id).where(Vendor.id == vendor_id)
    )
    vendor_with_user = result.first()

    if not vendor_with_user:
        raise HTTPException(status_code=404, detail="Vendor not found")

    vendor, user = vendor_with_user

    # Update KYC status
    vendor.kyc_status = KYCStatus.REJECTED
    vendor.kyc_reviewed_at = func.now()
    vendor.kyc_reviewer_id = current_admin.id
    await db.commit()

    # Send KYC rejection email
    try:
        await email_service.send_vendor_kyc_rejected_email(
            email=user.email,
            vendor_name=user.full_name or vendor.business_name,
            business_name=vendor.business_name,
            reason=reason
        )
    except Exception as e:
        print(f"Error sending KYC rejection email: {e}")

    return {
        "message": "Vendor KYC rejected successfully",
        "vendor_id": str(vendor_id),
        "kyc_status": vendor.kyc_status.value,
        "kyc_reviewed_at": vendor.kyc_reviewed_at.isoformat(),
        "reason": reason
    }


# ==================== VENDOR APPLICATION MANAGEMENT ====================

@router.get("/vendor-applications")
async def list_vendor_applications(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    status: str = Query("pending_review", description="Filter by status"),
    search: Optional[str] = Query(None, description="Search by name or email"),
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    List all vendor applications with pagination and filtering
    
    Requires admin role
    """
    # Build query
    query = select(VendorApplication)
    
    # Apply filters
    filters = [VendorApplication.status == status]
    
    if search:
        search_term = f"%{search}%"
        filters.append(
            or_(
                VendorApplication.first_name.ilike(search_term),
                VendorApplication.last_name.ilike(search_term),
                VendorApplication.email.ilike(search_term),
                VendorApplication.business_name.ilike(search_term)
            )
        )
    
    query = query.where(*filters)
    
    # Get total count
    count_query = select(func.count()).select_from(VendorApplication).where(*filters)
    result = await db.execute(count_query)
    total = result.scalar()
    
    # Apply pagination
    query = query.order_by(VendorApplication.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    
    result = await db.execute(query)
    applications = result.scalars().all()

    vendor_by_id = {}
    if applications:
        vendor_ids = [app.vendor_id for app in applications if app.vendor_id]
        if vendor_ids:
            vendor_result = await db.execute(
                select(Vendor, User)
                .join(User, Vendor.user_id == User.id)
                .where(Vendor.id.in_(vendor_ids))
            )
            vendor_by_id = {
                str(vendor.id): (vendor, user)
                for vendor, user in vendor_result.all()
            }
    
    # Calculate pagination info
    total_pages = (total + page_size - 1) // page_size
    
    return {
        "items": [
            {
                "id": str(app.id),
                "first_name": app.first_name,
                "last_name": app.last_name,
                "email": app.email,
                "phone_country_code": app.phone_country_code,
                "phone_number": app.phone_number,
                "business_name": app.business_name,
                "business_location": app.business_location,
                "product_categories": app.product_categories,
                "local_production_level": app.local_production_level,
                "years_in_business": app.years_in_business,
                "brand_story": app.brand_story,
                "website_link": app.website_link,
                "social_media_handles": app.social_media_handles,
                "status": app.status,
                "admin_notes": app.admin_notes,
                "vendor_id": str(app.vendor_id) if app.vendor_id else None,
                "created_at": app.created_at.isoformat() if app.created_at else None,
                "reviewed_at": app.reviewed_at.isoformat() if app.reviewed_at else None,
                "vendor_user_id": (
                    str(vendor_by_id[str(app.vendor_id)][1].id)
                    if app.vendor_id and str(app.vendor_id) in vendor_by_id
                    else None
                ),
                "vendor_user_is_active": (
                    vendor_by_id[str(app.vendor_id)][1].is_active
                    if app.vendor_id and str(app.vendor_id) in vendor_by_id
                    else None
                ),
                "vendor_is_onboarding": (
                    vendor_by_id[str(app.vendor_id)][0].is_onboarding
                    if app.vendor_id and str(app.vendor_id) in vendor_by_id
                    else None
                ),
                "vendor_brand_info_completed": (
                    vendor_by_id[str(app.vendor_id)][0].brand_info_completed
                    if app.vendor_id and str(app.vendor_id) in vendor_by_id
                    else None
                ),
                "vendor_payout_info_completed": (
                    vendor_by_id[str(app.vendor_id)][0].payout_info_completed
                    if app.vendor_id and str(app.vendor_id) in vendor_by_id
                    else None
                ),
            }
            for app in applications
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }


@router.get("/vendor-applications/{application_id}")
async def get_vendor_application(
    application_id: UUID,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Get detailed vendor application information
    
    Requires admin role
    """
    result = await db.execute(
        select(VendorApplication).where(VendorApplication.id == application_id)
    )
    application = result.scalar_one_or_none()
    
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    
    vendor_user = None
    vendor = None
    if application.vendor_id:
        vendor_result = await db.execute(
            select(Vendor, User)
            .join(User, Vendor.user_id == User.id)
            .where(Vendor.id == application.vendor_id)
        )
        vendor_row = vendor_result.first()
        if vendor_row:
            vendor, vendor_user = vendor_row

    return {
        "id": str(application.id),
        "first_name": application.first_name,
        "last_name": application.last_name,
        "email": application.email,
        "phone_country_code": application.phone_country_code,
        "phone_number": application.phone_number,
        "business_name": application.business_name,
        "business_location": application.business_location,
        "is_business_registered": application.is_business_registered,
        "product_categories": application.product_categories,
        "local_production_level": application.local_production_level,
        "years_in_business": application.years_in_business,
        "brand_story": application.brand_story,
        "website_link": application.website_link,
        "social_media_handles": application.social_media_handles,
        "status": application.status,
        "admin_notes": application.admin_notes,
        "reviewed_by": str(application.reviewed_by) if application.reviewed_by else None,
        "reviewed_at": application.reviewed_at.isoformat() if application.reviewed_at else None,
        "vendor_id": str(application.vendor_id) if application.vendor_id else None,
        "vendor_user_id": str(vendor_user.id) if vendor_user else None,
        "vendor_user_is_active": vendor_user.is_active if vendor_user else None,
        "vendor_is_onboarding": vendor.is_onboarding if vendor else None,
        "vendor_brand_info_completed": vendor.brand_info_completed if vendor else None,
        "vendor_payout_info_completed": vendor.payout_info_completed if vendor else None,
        "created_at": application.created_at.isoformat() if application.created_at else None,
        "updated_at": application.updated_at.isoformat() if application.updated_at else None,
    }


@router.put("/vendor-applications/{application_id}/notes")
async def update_application_notes(
    application_id: UUID,
    admin_notes: str = Query(..., description="Admin notes for the application"),
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Update admin notes for a vendor application

    Requires admin role
    """
    result = await db.execute(
        select(VendorApplication).where(VendorApplication.id == application_id)
    )
    application = result.scalar_one_or_none()

    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    application.admin_notes = admin_notes

    await db.commit()
    await db.refresh(application)

    return {
        "message": "Notes updated successfully",
        "application_id": str(application.id),
        "admin_notes": application.admin_notes
    }


@router.post("/vendor-applications/{application_id}/resend-activation")
async def resend_vendor_activation(
    application_id: UUID,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Resend vendor activation email for approved applications

    Requires admin role
    """
    from app.services.vendor_otp_service import VendorOTPService

    application_result = await db.execute(
        select(VendorApplication).where(VendorApplication.id == application_id)
    )
    application = application_result.scalar_one_or_none()

    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    if application.status != "approved":
        raise HTTPException(status_code=400, detail="Activation can only be resent for approved applications")

    if not application.vendor_id:
        raise HTTPException(status_code=400, detail="Approved application is missing vendor record")

    vendor_result = await db.execute(
        select(Vendor, User)
        .join(User, Vendor.user_id == User.id)
        .where(Vendor.id == application.vendor_id)
    )
    vendor_row = vendor_result.first()

    if not vendor_row:
        raise HTTPException(status_code=404, detail="Vendor record not found for this application")

    vendor, vendor_user = vendor_row

    setup_complete = (
        vendor_user.is_active
        and not vendor.is_onboarding
        and vendor.brand_info_completed
        and vendor.payout_info_completed
    )

    if setup_complete:
        raise HTTPException(status_code=400, detail="Vendor account is already active and fully onboarded")

    await VendorOTPService.create_and_send_otp(
        db=db,
        vendor_id=vendor.id,
        email=vendor_user.email
    )

    return {
        "message": "Activation email resent successfully",
        "email": vendor_user.email
    }


@router.post("/vendors/{vendor_id}/restore")
async def restore_vendor_store(
    vendor_id: UUID,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Restore a deleted vendor store

    This endpoint allows admins to restore a vendor store that has been soft-deleted.
    The store will be reactivated and the deletion timestamp will be cleared.
    An email notification will be sent to the vendor.

    Requires admin role
    """
    from datetime import datetime
    from app.services.email_service import email_service
    import logging

    logger = logging.getLogger(__name__)

    # Get vendor with user information
    result = await db.execute(
        select(Vendor, User).join(User, Vendor.user_id == User.id).where(Vendor.id == vendor_id)
    )
    vendor_with_user = result.first()

    if not vendor_with_user:
        raise HTTPException(status_code=404, detail="Vendor not found")

    vendor, user = vendor_with_user

    # Check if store is actually deleted
    if not vendor.store_deleted_at:
        raise HTTPException(
            status_code=400,
            detail="Store is not deleted. Only deleted stores can be restored."
        )

    # Restore the store
    vendor.store_deleted_at = None
    vendor.store_active = True
    vendor.store_paused_at = None  # Clear paused status as well

    await db.commit()
    await db.refresh(vendor)

    # Send email notification to vendor
    try:
        await email_service.send_vendor_store_restored_email(
            email=user.email,
            vendor_name=user.full_name or "Vendor",
            business_name=vendor.business_name
        )
        logger.info(f"Store restoration email sent to {user.email}")
    except Exception as e:
        # Log error but don't fail the restore operation
        logger.error(f"Failed to send restoration email to {user.email}: {e}")

    return {
        "message": "Vendor store restored successfully",
        "vendor_id": str(vendor.id),
        "business_name": vendor.business_name,
        "store_active": vendor.store_active,
        "store_deleted_at": None,
        "restored_at": datetime.utcnow().isoformat(),
        "restored_by": str(current_admin.id),
        "email_sent": True  # Always return True since we don't want to expose email delivery status
    }


# ==================== PRODUCT MANAGEMENT ENDPOINTS ====================

@router.get("/products")
async def list_all_products(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    search: Optional[str] = Query(None, description="Search by product title or SKU"),
    status: Optional[ProductStatus] = Query(None, description="Filter by product status"),
    moderation_status: Optional[ModerationStatus] = Query(None, description="Filter by moderation status"),
    vendor_id: Optional[UUID] = Query(None, description="Filter by vendor ID"),
    category_id: Optional[UUID] = Query(None, description="Filter by category ID"),
    is_featured: Optional[bool] = Query(None, description="Filter by featured status"),
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    List all products with pagination and filtering

    Requires admin role
    """
    # Build query with vendor join
    query = select(Product, Vendor).join(Vendor, Product.vendor_id == Vendor.id)

    # Apply filters
    filters = []

    if search:
        search_term = f"%{search}%"
        filters.append(
            or_(
                Product.title.ilike(search_term),
                Product.sku.ilike(search_term)
            )
        )

    if status is not None:
        filters.append(Product.status == status)

    if moderation_status is not None:
        filters.append(Product.moderation_status == moderation_status)

    if vendor_id is not None:
        filters.append(Product.vendor_id == vendor_id)

    if category_id is not None:
        filters.append(Product.category_id == category_id)

    if is_featured is not None:
        filters.append(Product.is_featured == is_featured)

    if filters:
        query = query.where(*filters)

    # Get total count
    count_query = select(func.count()).select_from(Product).join(Vendor, Product.vendor_id == Vendor.id)
    if filters:
        count_query = count_query.where(*filters)

    result = await db.execute(count_query)
    total = result.scalar()

    # Apply pagination
    query = query.order_by(Product.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    products_with_vendors = result.all()

    # Calculate pagination info
    total_pages = (total + page_size - 1) // page_size

    return {
        "items": [
            {
                "id": str(product.id),
                "title": product.title,
                "description": product.description,
                "sku": product.sku,
                "base_price": float(product.base_price),
                "compare_at_price": float(product.compare_at_price) if product.compare_at_price else None,
                "total_stock": product.total_stock,
                "status": product.status.value,
                "is_featured": product.is_featured,
                "moderation_status": product.moderation_status.value,
                "moderated_at": product.moderated_at.isoformat() if product.moderated_at else None,
                "moderation_notes": product.moderation_notes,
                "views_count": product.views_count,
                "orders_count": product.orders_count,
                "vendor": {
                    "id": str(vendor.id),
                    "business_name": vendor.business_name,
                },
                "created_at": product.created_at.isoformat() if product.created_at else None,
                "updated_at": product.updated_at.isoformat() if product.updated_at else None,
            }
            for product, vendor in products_with_vendors
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }


@router.put("/products/{product_id}/feature")
async def update_product_featured(
    product_id: UUID,
    request: ProductFeatureUpdate,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Toggle featured status for an approved product

    Requires admin role
    """
    _ = current_admin

    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    if product.moderation_status != ModerationStatus.APPROVED:
        raise HTTPException(status_code=400, detail="Only approved products can be featured")

    product.is_featured = request.is_featured
    await db.commit()
    await db.refresh(product)

    return {
        "message": "Featured status updated",
        "product_id": str(product.id),
        "is_featured": product.is_featured,
    }


@router.put("/products/{product_id}/approve")
async def approve_product(
    product_id: UUID,
    request: ProductApprovalRequest,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Approve a product

    This endpoint approves a product for sale on the platform and sends
    an email notification to the vendor.

    Requires admin role
    """
    from datetime import datetime
    from app.services.email_service import email_service
    import logging

    logger = logging.getLogger(__name__)

    # Get product with vendor information
    result = await db.execute(
        select(Product, Vendor, User)
        .join(Vendor, Product.vendor_id == Vendor.id)
        .join(User, Vendor.user_id == User.id)
        .where(Product.id == product_id)
    )
    product_with_vendor = result.first()

    if not product_with_vendor:
        raise HTTPException(status_code=404, detail="Product not found")

    product, vendor, user = product_with_vendor

    # Check if already approved
    if product.moderation_status == ModerationStatus.APPROVED:
        raise HTTPException(status_code=400, detail="Product is already approved")

    # Update product status
    product.moderation_status = ModerationStatus.APPROVED
    product.moderated_at = datetime.utcnow()
    product.moderated_by = current_admin.id
    product.moderation_notes = request.notes

    # Set product to active if it was pending
    if product.status == ProductStatus.DRAFT:
        product.status = ProductStatus.ACTIVE

    await db.commit()
    await db.refresh(product)

    # Send email notification to vendor
    try:
        await email_service.send_product_approved_email(
            email=user.email,
            vendor_name=user.full_name or vendor.business_name,
            product_title=product.title,
            product_id=str(product.id),
            notes=request.notes
        )
        logger.info(f"Product approval email sent to {user.email} for product {product.id}")
    except Exception as e:
        # Log error but don't fail the approval operation
        logger.error(f"Failed to send approval email to {user.email}: {e}")

    return {
        "message": "Product approved successfully",
        "product_id": str(product.id),
        "title": product.title,
        "moderation_status": product.moderation_status.value,
        "status": product.status.value,
        "moderated_at": product.moderated_at.isoformat(),
        "moderated_by": str(current_admin.id),
        "email_sent": True
    }


@router.put("/products/{product_id}/reject")
async def reject_product(
    product_id: UUID,
    request: ProductRejectionRequest,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Reject a product

    This endpoint rejects a product from being sold on the platform and sends
    an email notification to the vendor with the rejection reason.

    Requires admin role
    """
    from datetime import datetime
    from app.services.email_service import email_service
    import logging

    logger = logging.getLogger(__name__)

    # Get product with vendor information
    result = await db.execute(
        select(Product, Vendor, User)
        .join(Vendor, Product.vendor_id == Vendor.id)
        .join(User, Vendor.user_id == User.id)
        .where(Product.id == product_id)
    )
    product_with_vendor = result.first()

    if not product_with_vendor:
        raise HTTPException(status_code=404, detail="Product not found")

    product, vendor, user = product_with_vendor

    # Update product status
    product.moderation_status = ModerationStatus.REJECTED
    product.moderated_at = datetime.utcnow()
    product.moderated_by = current_admin.id
    product.moderation_notes = f"REJECTION REASON: {request.reason}"
    if request.notes:
        product.moderation_notes += f"\n\nADMIN NOTES: {request.notes}"

    # Set product back to draft
    product.status = ProductStatus.DRAFT

    await db.commit()
    await db.refresh(product)

    # Send email notification to vendor
    try:
        await email_service.send_product_rejected_email(
            email=user.email,
            vendor_name=user.full_name or vendor.business_name,
            product_title=product.title,
            product_id=str(product.id),
            reason=request.reason,
            notes=request.notes
        )
        logger.info(f"Product rejection email sent to {user.email} for product {product.id}")
    except Exception as e:
        # Log error but don't fail the rejection operation
        logger.error(f"Failed to send rejection email to {user.email}: {e}")

    return {
        "message": "Product rejected successfully",
        "product_id": str(product.id),
        "title": product.title,
        "moderation_status": product.moderation_status.value,
        "status": product.status.value,
        "moderated_at": product.moderated_at.isoformat(),
        "moderated_by": str(current_admin.id),
        "rejection_reason": request.reason,
        "email_sent": True
    }


@router.delete("/products/{product_id}")
async def delete_product(
    product_id: UUID,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Delete a product permanently from the marketplace

    This endpoint permanently removes a product and all its associated data
    (variants, images, etc.) from the database.

    Requires admin role
    """
    import logging

    logger = logging.getLogger(__name__)

    # Get product
    result = await db.execute(
        select(Product).where(Product.id == product_id)
    )
    product = result.scalar_one_or_none()

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    product_title = product.title

    try:
        # Delete associated product images
        await db.execute(
            delete(ProductImage).where(ProductImage.product_id == product_id)
        )

        # Delete associated product variants
        await db.execute(
            delete(ProductVariant).where(ProductVariant.product_id == product_id)
        )

        # Delete the product itself
        await db.delete(product)
        await db.commit()

        logger.info(f"Admin {current_admin.id} deleted product {product_id} ({product_title})")

        return {
            "message": "Product deleted successfully",
            "product_id": str(product_id),
            "title": product_title
        }
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to delete product {product_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete product: {str(e)}"
        )


@router.get("/products/{product_id}")
async def get_product(
    product_id: UUID,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Get detailed product information

    Requires admin role
    """
    result = await db.execute(
        select(Product).where(Product.id == product_id)
    )
    product = result.scalar_one_or_none()

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # Get product images
    image_result = await db.execute(
        select(ProductImage).where(ProductImage.product_id == product_id)
    )
    images = image_result.scalars().all()

    # Get product variants
    variant_result = await db.execute(
        select(ProductVariant).where(ProductVariant.product_id == product_id)
    )
    variants = variant_result.scalars().all()

    return {
        "id": str(product.id),
        "title": product.title,
        "description": product.description,
        "sku": product.sku,
        "base_price": float(product.base_price),
        "compare_at_price": float(product.compare_at_price) if product.compare_at_price else None,
        "total_stock": product.total_stock,
        "status": product.status.value,
        "moderation_status": product.moderation_status.value,
        "is_featured": product.is_featured,
        "views_count": product.views_count,
        "orders_count": product.orders_count,
        "created_at": product.created_at.isoformat() if product.created_at else None,
        "updated_at": product.updated_at.isoformat() if product.updated_at else None,
        "images": [
            {
                "id": str(image.id),
                "image_url": image.image_url,
                "alt_text": image.alt_text,
                "is_primary": image.is_primary,
                "display_order": image.display_order,
            }
            for image in images
        ],
        "variants": [
            {
                "id": str(variant.id),
                "sku": variant.sku,
                "size": variant.size,
                "color": variant.color,
                "price": float(variant.price),
                "stock": variant.stock,
                "is_active": variant.is_active,
            }
            for variant in variants
        ]
    }


@router.put("/products/{product_id}")
async def update_product(
    product_id: UUID,
    product_data: dict,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Update a product

    Requires admin role
    """
    # Get product
    result = await db.execute(
        select(Product).where(Product.id == product_id)
    )
    product = result.scalar_one_or_none()

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # Update fields
    for field, value in product_data.items():
        if hasattr(product, field):
            setattr(product, field, value)

    await db.commit()
    await db.refresh(product)

    return {
        "message": "Product updated successfully",
        "product_id": str(product.id)
    }


@router.get("/products/{product_id}/variants")
async def get_product_variants(
    product_id: UUID,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Get all variants for a product

    Requires admin role
    """
    result = await db.execute(
        select(ProductVariant).where(ProductVariant.product_id == product_id)
    )
    variants = result.scalars().all()

    return {
        "product_id": str(product_id),
        "variants": [
            {
                "id": str(variant.id),
                "sku": variant.sku,
                "size": variant.size,
                "color": variant.color,
                "price": float(variant.price),
                "stock": variant.stock,
                "is_active": variant.is_active,
            }
            for variant in variants
        ]
    }


@router.put("/products/{product_id}/variants/{variant_id}")
async def update_product_variant(
    product_id: UUID,
    variant_id: UUID,
    variant_data: dict,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Update a product variant

    Requires admin role
    """
    # Get variant
    result = await db.execute(
        select(ProductVariant).where(ProductVariant.id == variant_id)
    )
    variant = result.scalar_one_or_none()

    if not variant:
        raise HTTPException(status_code=404, detail="Variant not found")

    # Update fields
    for field, value in variant_data.items():
        if hasattr(variant, field):
            setattr(variant, field, value)

    await db.commit()
    await db.refresh(variant)

    return {
        "message": "Variant updated successfully",
        "variant_id": str(variant.id)
    }


@router.delete("/products/{product_id}/variants/{variant_id}")
async def delete_product_variant(
    product_id: UUID,
    variant_id: UUID,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Delete a product variant

    Requires admin role
    """
    result = await db.execute(
        select(ProductVariant).where(ProductVariant.id == variant_id)
    )
    variant = result.scalar_one_or_none()

    if not variant:
        raise HTTPException(status_code=404, detail="Variant not found")

    await db.delete(variant)
    await db.commit()

    return {
        "message": "Variant deleted successfully",
        "variant_id": str(variant.id)
    }


# ==================== CATEGORIES AND COLLECTIONS MANAGEMENT ====================

@router.get("/categories")
async def list_categories(
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    List all categories

    Requires admin role
    """
    result = await db.execute(select(ProductCategory).order_by(ProductCategory.display_order))
    categories = result.scalars().all()

    return {
        "categories": [
            {
                "id": str(category.id),
                "name": category.name,
                "description": category.description,
                "slug": category.slug,
                "display_order": category.display_order,
                "is_featured": category.is_featured,
                "is_active": category.is_active,
                "parent_category_id": str(category.parent_category_id) if category.parent_category_id else None,
            }
            for category in categories
        ]
    }


@router.post("/categories")
async def create_category(
    category_data: dict,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new category

    Requires admin role
    """
    from app.models.product import ProductCategory

    category = ProductCategory(
        name=category_data.get("name"),
        description=category_data.get("description"),
        slug=category_data.get("slug"),
        display_order=category_data.get("display_order", 0),
        is_featured=category_data.get("is_featured", False),
        is_active=category_data.get("is_active", True),
        parent_category_id=category_data.get("parent_category_id")
    )

    db.add(category)
    await db.commit()
    await db.refresh(category)

    return {
        "message": "Category created successfully",
        "category": {
            "id": str(category.id),
            "name": category.name,
            "description": category.description,
            "slug": category.slug,
            "display_order": category.display_order,
            "is_featured": category.is_featured,
            "is_active": category.is_active,
            "parent_category_id": str(category.parent_category_id) if category.parent_category_id else None,
        }
    }


@router.put("/categories/{category_id}")
async def update_category(
    category_id: UUID,
    category_data: dict,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Update a category

    Requires admin role
    """
    from app.models.product import ProductCategory

    result = await db.execute(select(ProductCategory).where(ProductCategory.id == category_id))
    category = result.scalar_one_or_none()

    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    # Update fields
    for field, value in category_data.items():
        if hasattr(category, field):
            setattr(category, field, value)

    await db.commit()
    await db.refresh(category)

    return {
        "message": "Category updated successfully",
        "category": {
            "id": str(category.id),
            "name": category.name,
            "description": category.description,
            "slug": category.slug,
            "display_order": category.display_order,
            "is_featured": category.is_featured,
            "is_active": category.is_active,
            "parent_category_id": str(category.parent_category_id) if category.parent_category_id else None,
        }
    }


@router.delete("/categories/{category_id}")
async def delete_category(
    category_id: UUID,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Delete a category

    Requires admin role
    """
    from app.models.product import ProductCategory

    result = await db.execute(select(ProductCategory).where(ProductCategory.id == category_id))
    category = result.scalar_one_or_none()

    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    await db.delete(category)
    await db.commit()

    return {
        "message": "Category deleted successfully",
        "category_id": str(category.id)
    }


@router.get("/collections")
async def list_collections(
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    List all collections

    Requires admin role
    """
    from app.models.product import ProductCollection

    result = await db.execute(select(ProductCollection).order_by(ProductCollection.display_order))
    collections = result.scalars().all()

    return {
        "collections": [
            {
                "id": str(collection.id),
                "title": collection.title,
                "description": collection.description,
                "slug": collection.slug,
                "image_url": collection.image_url,
                "display_order": collection.display_order,
                "is_featured": collection.is_featured,
                "is_active": collection.is_active,
            }
            for collection in collections
        ]
    }


@router.post("/collections")
async def create_collection(
    collection_data: dict,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new collection

    Requires admin role
    """
    from app.models.product import ProductCollection

    collection = ProductCollection(
        title=collection_data.get("title"),
        description=collection_data.get("description"),
        slug=collection_data.get("slug"),
        image_url=collection_data.get("image_url"),
        display_order=collection_data.get("display_order", 0),
        is_featured=collection_data.get("is_featured", False),
        is_active=collection_data.get("is_active", True)
    )

    db.add(collection)
    await db.commit()
    await db.refresh(collection)

    return {
        "message": "Collection created successfully",
        "collection": {
            "id": str(collection.id),
            "title": collection.title,
            "description": collection.description,
            "slug": collection.slug,
            "image_url": collection.image_url,
            "display_order": collection.display_order,
            "is_featured": collection.is_featured,
            "is_active": collection.is_active,
        }
    }


@router.put("/collections/{collection_id}")
async def update_collection(
    collection_id: UUID,
    collection_data: dict,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Update a collection

    Requires admin role
    """
    from app.models.product import ProductCollection

    result = await db.execute(select(ProductCollection).where(ProductCollection.id == collection_id))
    collection = result.scalar_one_or_none()

    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    # Update fields
    for field, value in collection_data.items():
        if hasattr(collection, field):
            setattr(collection, field, value)

    await db.commit()
    await db.refresh(collection)

    return {
        "message": "Collection updated successfully",
        "collection": {
            "id": str(collection.id),
            "title": collection.title,
            "description": collection.description,
            "slug": collection.slug,
            "image_url": collection.image_url,
            "display_order": collection.display_order,
            "is_featured": collection.is_featured,
            "is_active": collection.is_active,
        }
    }


@router.delete("/collections/{collection_id}")
async def delete_collection(
    collection_id: UUID,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Delete a collection

    Requires admin role
    """
    from app.models.product import ProductCollection

    result = await db.execute(select(ProductCollection).where(ProductCollection.id == collection_id))
    collection = result.scalar_one_or_none()

    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    await db.delete(collection)
    await db.commit()

    return {
        "message": "Collection deleted successfully",
        "collection_id": str(collection.id)
    }


@router.get("/collections/{collection_id}")
async def get_collection(
    collection_id: UUID,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Get detailed collection information

    Requires admin role
    """
    from app.models.product import ProductCollection

    result = await db.execute(select(ProductCollection).where(ProductCollection.id == collection_id))
    collection = result.scalar_one_or_none()

    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    return {
        "id": str(collection.id),
        "title": collection.title,
        "description": collection.description,
        "slug": collection.slug,
        "image_url": collection.image_url,
        "display_order": collection.display_order,
        "is_featured": collection.is_featured,
        "is_active": collection.is_active,
        "created_at": collection.created_at.isoformat() if collection.created_at else None,
        "updated_at": collection.updated_at.isoformat() if collection.updated_at else None,
    }


@router.get("/collections/{collection_id}/products")
async def get_collection_products(
    collection_id: UUID,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Get products in a collection

    Requires admin role
    """
    from app.models.product import ProductCollection

    # Get collection with products
    result = await db.execute(
        select(ProductCollection).where(ProductCollection.id == collection_id)
    )
    collection = result.scalar_one_or_none()

    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    return {
        "collection_id": str(collection.id),
        "collection_title": collection.title,
        "products": [
            {
                "id": str(product.id),
                "title": product.title,
                "description": product.description,
                "sku": product.sku,
                "base_price": float(product.base_price),
                "compare_at_price": float(product.compare_at_price) if product.compare_at_price else None,
                "total_stock": product.total_stock,
                "status": product.status.value,
                "is_featured": product.is_featured,
                "moderation_status": product.moderation_status.value,
                "created_at": product.created_at.isoformat() if product.created_at else None,
                "updated_at": product.updated_at.isoformat() if product.updated_at else None,
            }
            for product in collection.products
        ]
    }


# ==================== SITE SETTINGS MANAGEMENT ====================

@router.get("/settings")
async def get_settings(
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Get system settings

    Requires admin role
    """
    from app.models.settings import Settings

    result = await db.execute(select(Settings))
    settings = result.scalar_one_or_none()

    if not settings:
        raise HTTPException(status_code=404, detail="Settings not found")

    return {
        "id": str(settings.id),
        "site_name": settings.site_name,
        "site_description": settings.site_description,
        "site_logo_url": settings.site_logo_url,
        "site_favicon_url": settings.site_favicon_url,
        "support_email": settings.support_email,
        "support_phone": settings.support_phone,
        "social_media_links": settings.social_media_links,
        "commission_rate": float(settings.commission_rate) if settings.commission_rate else 0.0,
        "payout_frequency": settings.payout_frequency,
        "payout_hold_days": settings.payout_hold_days,
        "maintenance_mode": settings.maintenance_mode,
        "maintenance_message": settings.maintenance_message,
        "maintenance_start": settings.maintenance_start.isoformat() if settings.maintenance_start else None,
        "maintenance_end": settings.maintenance_end.isoformat() if settings.maintenance_end else None,
        "created_at": settings.created_at.isoformat() if settings.created_at else None,
        "updated_at": settings.updated_at.isoformat() if settings.updated_at else None,
    }


@router.put("/settings")
async def update_settings(
    settings_data: dict,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Update system settings

    Requires admin role
    """
    from app.models.settings import Settings

    result = await db.execute(select(Settings))
    settings = result.scalar_one_or_none()

    if not settings:
        raise HTTPException(status_code=404, detail="Settings not found")

    # Update fields
    for field, value in settings_data.items():
        if hasattr(settings, field):
            setattr(settings, field, value)

    await db.commit()
    await db.refresh(settings)

    return {
        "message": "Settings updated successfully",
        "settings_id": str(settings.id)
    }


@router.get("/settings/featured-products")
async def get_featured_products(
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Get featured products

    Requires admin role
    """
    result = await db.execute(select(Product).where(Product.is_featured == True))
    featured_products = result.scalars().all()

    return {
        "products": [
            {
                "id": str(product.id),
                "title": product.title,
                "description": product.description,
                "sku": product.sku,
                "base_price": float(product.base_price),
                "compare_at_price": float(product.compare_at_price) if product.compare_at_price else None,
                "total_stock": product.total_stock,
                "status": product.status.value,
                "is_featured": product.is_featured,
                "moderation_status": product.moderation_status.value,
            }
            for product in featured_products
        ]
    }


@router.put("/settings/featured-products")
async def update_featured_products(
    product_ids: List[UUID],
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Update featured products

    Requires admin role
    """
    # Clear existing featured status
    await db.execute(
        update(Product)
        .where(Product.is_featured == True)
        .values(is_featured=False)
    )

    # Set new featured products
    await db.execute(
        update(Product)
        .where(Product.id.in_(product_ids))
        .values(is_featured=True)
    )

    await db.commit()

    return {
        "message": "Featured products updated",
        "count": len(product_ids)
    }


# ==================== ORDERS MANAGEMENT ====================

@router.get("/orders")
async def list_orders(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    search: Optional[str] = Query(None, description="Search by order number or customer name"),
    status: Optional[str] = Query(None, description="Filter by status"),
    payment_status: Optional[str] = Query(None, description="Filter by payment status"),
    fulfillment_status: Optional[str] = Query(None, description="Filter by fulfillment status"),
    vendor_id: Optional[UUID] = Query(None, description="Filter by vendor ID"),
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    List all orders with pagination and filtering

    Requires admin role
    """
    from app.models.order import Order

    # Build query
    query = (
        select(Order, User)
        .join(User, Order.customer_id == User.id)
        .options(selectinload(Order.items))
    )

    # Apply filters
    filters = []

    if search:
        search_term = f"%{search}%"
        filters.append(
            or_(
                Order.order_number.ilike(search_term),
                User.full_name.ilike(search_term),
                User.email.ilike(search_term)
            )
        )

    if status is not None:
        filters.append(Order.fulfillment_status == status)

    if payment_status is not None:
        filters.append(Order.payment_status == payment_status)

    if fulfillment_status is not None:
        filters.append(Order.fulfillment_status == fulfillment_status)

    if vendor_id is not None:
        filters.append(Order.vendor_id == vendor_id)

    if filters:
        query = query.where(*filters)

    # Get total count
    count_query = select(func.count()).select_from(Order).join(User, Order.customer_id == User.id)
    if filters:
        count_query = count_query.where(*filters)

    result = await db.execute(count_query)
    total = result.scalar()

    # Apply pagination
    query = query.order_by(Order.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    orders_with_users = result.all()

    # Calculate pagination info
    total_pages = (total + page_size - 1) // page_size

    orders_data = []
    for order, user in orders_with_users:
        vendor_ids = {item.vendor_id for item in order.items}
        item_count = sum(item.quantity for item in order.items)

        orders_data.append(
            {
                "id": str(order.id),
                "order_number": order.order_number,
                "customer": {
                    "id": str(user.id),
                    "full_name": user.full_name,
                    "email": user.email,
                },
                "total_amount": float(order.total_amount),
                "payment_status": order.payment_status,
                "fulfillment_status": order.fulfillment_status,
                "created_at": order.created_at.isoformat() if order.created_at else None,
                "vendor_count": len(vendor_ids),
                "item_count": item_count,
            }
        )

    return {
        "orders": orders_data,
        "items": orders_data,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }


@router.get("/orders/stats")
async def get_order_statistics(
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Get order statistics for admin dashboard

    Requires admin role
    """
    from app.models.order import Order, PaymentStatus, FulfillmentStatus

    total_query = select(
        func.count(Order.id).label("total_orders"),
        func.coalesce(func.sum(Order.total_amount), 0).label("total_revenue"),
    )
    total_result = await db.execute(total_query)
    total_row = total_result.one()

    pending_count = await db.scalar(
        select(func.count(Order.id)).where(Order.fulfillment_status == FulfillmentStatus.ORDER_RECEIVED)
    ) or 0

    processing_count = await db.scalar(
        select(func.count(Order.id)).where(Order.fulfillment_status == FulfillmentStatus.PREPARING_FOR_PICKUP)
    ) or 0

    shipped_count = await db.scalar(
        select(func.count(Order.id)).where(Order.fulfillment_status == FulfillmentStatus.IN_TRANSIT)
    ) or 0

    delivered_count = await db.scalar(
        select(func.count(Order.id)).where(Order.fulfillment_status == FulfillmentStatus.DELIVERED)
    ) or 0

    cancelled_count = await db.scalar(
        select(func.count(Order.id)).where(Order.fulfillment_status == FulfillmentStatus.CANCELLED)
    ) or 0

    pending_payment = await db.scalar(
        select(func.count(Order.id)).where(Order.payment_status == PaymentStatus.PENDING)
    ) or 0

    failed_payment = await db.scalar(
        select(func.count(Order.id)).where(Order.payment_status == PaymentStatus.FAILED)
    ) or 0

    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_stats = await db.execute(
        select(
            func.count(Order.id).label("orders_today"),
            func.coalesce(func.sum(Order.total_amount), 0).label("revenue_today"),
        ).where(Order.created_at >= today_start)
    )
    today_row = today_stats.one()

    average_order_value = Decimal("0.00")
    if total_row.total_orders > 0:
        average_order_value = total_row.total_revenue / total_row.total_orders

    return {
        "total_orders": total_row.total_orders,
        "total_revenue": float(total_row.total_revenue),
        "pending_orders": pending_count,
        "processing_orders": processing_count,
        "shipped_orders": shipped_count,
        "delivered_orders": delivered_count,
        "cancelled_orders": cancelled_count,
        "pending_payment": pending_payment,
        "failed_payment": failed_payment,
        "average_order_value": float(average_order_value),
        "orders_today": today_row.orders_today,
        "revenue_today": float(today_row.revenue_today),
    }


@router.get("/orders/{order_id}")
async def get_order(
    order_id: UUID,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Get detailed order information

    Requires admin role
    """
    from app.models.order import Order, OrderItem
    from app.models.product import Product

    # Get order
    result = await db.execute(
        select(Order, User)
        .join(User, Order.customer_id == User.id)
        .where(Order.id == order_id)
    )
    order_with_user = result.first()

    if not order_with_user:
        raise HTTPException(status_code=404, detail="Order not found")

    order, user = order_with_user

    # Get order items
    items_result = await db.execute(
        select(OrderItem)
        .where(OrderItem.order_id == order_id)
        .options(
            selectinload(OrderItem.vendor),
            selectinload(OrderItem.product).selectinload(Product.images),
        )
    )
    items = items_result.scalars().all()

    return {
        "id": str(order.id),
        "order_number": order.order_number,
        "customer": {
            "id": str(user.id),
            "full_name": user.full_name,
            "email": user.email,
        },
        "total_amount": float(order.total_amount),
        "payment_status": order.payment_status,
        "fulfillment_status": order.fulfillment_status,
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "items": [
            {
                "id": str(item.id),
                "product_title": item.product_title,
                "quantity": item.quantity,
                "unit_price": float(item.unit_price),
                "subtotal": float(item.subtotal),
                "fulfillment_status": item.fulfillment_status,
                "product_image_url": (
                    (
                        (next((img for img in item.product.images if img.is_primary), None) or item.product.images[0])
                        .image_url
                    )
                    if item.product and item.product.images
                    else None
                ),
                "vendor": {
                    "id": str(item.vendor.id),
                    "business_name": item.vendor.business_name,
                }
            }
            for item in items
        ]
    }


@router.put("/orders/{order_id}/status")
async def update_order_status(
    order_id: UUID,
    status: str = Query(..., description="New fulfillment status"),
    notes: Optional[str] = Query(None, description="Admin notes"),
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Update order status

    Requires admin role
    """
    from app.models.order import Order
    from app.services.email_service import email_service
    import logging

    logger = logging.getLogger(__name__)

    # Get order
    result = await db.execute(
        select(Order, User).join(User, Order.customer_id == User.id).where(Order.id == order_id)
    )
    order_with_user = result.first()

    if not order_with_user:
        raise HTTPException(status_code=404, detail="Order not found")

    order, user = order_with_user

    # Update status
    order.fulfillment_status = status
    order.admin_notes = notes
    await db.commit()

    # Send email notification
    try:
        await email_service.send_order_status_update_email(
            email=user.email,
            customer_name=user.full_name,
            order_number=order.order_number,
            status=status,
            notes=notes
        )
    except Exception as e:
        logger.error(f"Error sending order status update email: {e}")

    return {
        "message": "Order status updated",
        "order_id": str(order.id),
        "status": status
    }


@router.post("/orders/{order_id}/cancel")
async def cancel_order(
    order_id: UUID,
    reason: str = Query(..., description="Reason for cancellation"),
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Cancel an order

    Requires admin role
    """
    from app.models.order import Order
    from app.services.email_service import email_service
    import logging

    logger = logging.getLogger(__name__)

    # Get order
    result = await db.execute(
        select(Order, User).join(User, Order.customer_id == User.id).where(Order.id == order_id)
    )
    order_with_user = result.first()

    if not order_with_user:
        raise HTTPException(status_code=404, detail="Order not found")

    order, user = order_with_user

    # Update status
    order.fulfillment_status = "cancelled"
    order.cancellation_reason = reason
    await db.commit()

    # Send cancellation email
    try:
        await email_service.send_order_cancellation_email(
            email=user.email,
            customer_name=user.full_name,
            order_number=order.order_number,
            reason=reason
        )
    except Exception as e:
        logger.error(f"Error sending cancellation email: {e}")

    return {
        "message": "Order cancelled",
        "order_id": str(order.id),
        "reason": reason
    }


@router.put("/orders/{order_id}/notes")
async def update_order_notes(
    order_id: UUID,
    notes: str = Query(..., description="Admin notes"),
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Update order notes

    Requires admin role
    """
    from app.models.order import Order

    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()

    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    order.admin_notes = notes
    await db.commit()

    return {
        "message": "Order notes updated",
        "order_id": str(order_id),
        "notes": notes
    }


@router.get("/orders/{order_id}/items")
async def get_order_items(
    order_id: UUID,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Get order items

    Requires admin role
    """
    from app.models.order import OrderItem

    result = await db.execute(select(OrderItem).where(OrderItem.order_id == order_id))
    items = result.scalars().all()

    return {
        "order_id": str(order_id),
        "items": [
            {
                "id": str(item.id),
                "product_title": item.product_title,
                "quantity": item.quantity,
                "unit_price": float(item.unit_price),
                "subtotal": float(item.subtotal),
                "fulfillment_status": item.fulfillment_status,
                "vendor": {
                    "id": str(item.vendor.id),
                    "business_name": item.vendor.business_name,
                }
            }
            for item in items
        ]
    }


@router.get("/orders/{order_id}/payments")
async def get_order_payments(
    order_id: UUID,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Get order payments

    Requires admin role
    """
    from app.models.payment import Payment

    result = await db.execute(select(Payment).where(Payment.order_id == order_id))
    payments = result.scalars().all()

    return {
        "order_id": str(order_id),
        "payments": [
            {
                "id": str(payment.id),
                "amount": float(payment.amount),
                "gateway": payment.payment_gateway.value,
                "status": payment.status.value,
                "created_at": payment.created_at.isoformat() if payment.created_at else None,
            }
            for payment in payments
        ]
    }


@router.get("/orders/{order_id}/returns")
async def get_order_returns(
    order_id: UUID,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Get order returns

    Requires admin role
    """
    from app.models.returns import Return

    result = await db.execute(select(Return).where(Return.order_id == order_id))
    returns = result.scalars().all()

    return {
        "order_id": str(order_id),
        "returns": [
            {
                "id": str(ret.id),
                "return_number": ret.return_number,
                "reason": ret.reason,
                "status": ret.status.value,
                "created_at": ret.created_at.isoformat() if ret.created_at else None,
            }
            for ret in returns
        ]
    }


@router.get("/orders/{order_id}/pickups")
async def get_order_pickups(
    order_id: UUID,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Get order pickups

    Requires admin role
    """
    from app.models.vendor_pickup import VendorPickup

    result = await db.execute(select(VendorPickup).where(VendorPickup.order_id == order_id))
    pickups = result.scalars().all()

    return {
        "order_id": str(order_id),
        "pickups": [
            {
                "id": str(pickup.id),
                "status": pickup.status.value,
                "pickup_date": pickup.scheduled_pickup_date.isoformat() if pickup.scheduled_pickup_date else None,
                "courier": pickup.courier_name,
                "tracking_number": pickup.tracking_number,
                "created_at": pickup.created_at.isoformat() if pickup.created_at else None,
            }
            for pickup in pickups
        ]
    }


# ==================== PAYOUT MANAGEMENT ====================

@router.get("/payouts")
async def list_payouts(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    status: Optional[str] = Query(None, description="Filter by status"),
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    List all payouts with pagination and filtering

    Requires admin role
    """
    from app.models.payment import Payout

    query = select(Payout, Vendor, User).join(Vendor, Payout.vendor_id == Vendor.id).join(User, Vendor.user_id == User.id)

    # Apply filters
    filters = []

    if status:
        filters.append(Payout.status == status)

    if filters:
        query = query.where(*filters)

    # Get total count
    count_query = select(func.count()).select_from(Payout)
    if filters:
        count_query = count_query.where(*filters)

    result = await db.execute(count_query)
    total = result.scalar()

    # Apply pagination
    query = query.order_by(Payout.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    payouts_with_vendors = result.all()

    # Calculate pagination info
    total_pages = (total + page_size - 1) // page_size

    return {
        "items": [
            {
                "id": str(payout.id),
                "vendor": {
                    "id": str(vendor.id),
                    "business_name": vendor.business_name,
                    "email": user.email,
                },
                "period_start": payout.payout_period_start.isoformat(),
                "period_end": payout.payout_period_end.isoformat(),
                "total_sales": float(payout.total_sales),
                "commission": float(payout.commission_amount),
                "payout_amount": float(payout.payout_amount),
                "status": payout.status.value,
                "created_at": payout.created_at.isoformat(),
            }
            for payout, vendor, user in payouts_with_vendors
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }


@router.get("/payouts/{payout_id}")
async def get_payout(
    payout_id: UUID,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Get detailed payout information

    Requires admin role
    """
    from app.models.payment import Payout

    result = await db.execute(
        select(Payout, Vendor, User)
        .join(Vendor, Payout.vendor_id == Vendor.id)
        .join(User, Vendor.user_id == User.id)
        .where(Payout.id == payout_id)
    )
    payout_with_vendor = result.first()

    if not payout_with_vendor:
        raise HTTPException(status_code=404, detail="Payout not found")

    payout, vendor, user = payout_with_vendor

    return {
        "id": str(payout.id),
        "vendor": {
            "id": str(vendor.id),
            "business_name": vendor.business_name,
            "email": user.email,
        },
        "period_start": payout.payout_period_start.isoformat(),
        "period_end": payout.payout_period_end.isoformat(),
        "total_sales": float(payout.total_sales),
        "commission": float(payout.commission_amount),
        "payout_amount": float(payout.payout_amount),
        "status": payout.status.value,
        "processed_at": payout.processed_at.isoformat() if payout.processed_at else None,
        "processed_by": str(payout.processed_by) if payout.processed_by else None,
        "payment_reference": payout.payment_reference,
        "notes": payout.notes,
        "created_at": payout.created_at.isoformat(),
    }


@router.put("/payouts/{payout_id}/process")
async def process_payout(
    payout_id: UUID,
    status: str = Query(..., description="New payout status"),
    payment_reference: Optional[str] = Query(None, description="Payment reference"),
    notes: Optional[str] = Query(None, description="Admin notes"),
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Process a payout

    Requires admin role
    """
    from app.models.payment import Payout
    from app.services.email_service import email_service
    import logging

    logger = logging.getLogger(__name__)

    # Get payout
    result = await db.execute(select(Payout).where(Payout.id == payout_id))
    payout = result.scalar_one_or_none()

    if not payout:
        raise HTTPException(status_code=404, detail="Payout not found")

    # Update payout status
    payout.status = status
    payout.processed_at = func.now()
    payout.processed_by = current_admin.id
    payout.payment_reference = payment_reference
    payout.notes = notes
    await db.commit()

    # Send email notification
    try:
        if status == "completed":
            await email_service.send_vendor_payout_processed_email(
                email=payout.vendor.user.email,
                vendor_name=payout.vendor.user.full_name or payout.vendor.business_name,
                business_name=payout.vendor.business_name,
                payout_amount=float(payout.payout_amount),
                payout_period=f"{payout.payout_period_start} to {payout.payout_period_end}",
                payment_reference=payment_reference
            )
        elif status == "failed":
            await email_service.send_vendor_payout_failed_email(
                email=payout.vendor.user.email,
                vendor_name=payout.vendor.user.full_name or payout.vendor.business_name,
                business_name=payout.vendor.business_name,
                payout_amount=float(payout.payout_amount),
                payout_period=f"{payout.payout_period_start} to {payout.payout_period_end}",
                failure_reason=notes or "Processing failed"
            )
    except Exception as e:
        # Log error but don't fail operation
        logger.error(f"Failed to send payout email: {e}")

    return {
        "message": "Payout processed",
        "payout_id": str(payout.id),
        "status": status,
        "processed_at": payout.processed_at.isoformat(),
        "processed_by": str(current_admin.id),
    }


@router.post("/payouts/{payout_id}/mark-paid")
async def mark_payout_paid(
    payout_id: UUID,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Mark payout as paid

    Requires admin role
    """
    from app.models.payment import Payout
    from app.services.email_service import email_service
    import logging

    logger = logging.getLogger(__name__)

    # Get payout
    result = await db.execute(select(Payout).where(Payout.id == payout_id))
    payout = result.scalar_one_or_none()

    if not payout:
        raise HTTPException(status_code=404, detail="Payout not found")

    # Update payout status
    payout.status = "completed"
    payout.processed_at = func.now()
    payout.processed_by = current_admin.id
    await db.commit()

    # Send email notification
    try:
        await email_service.send_vendor_payout_processed_email(
            email=payout.vendor.user.email,
            vendor_name=payout.vendor.user.full_name or payout.vendor.business_name,
            business_name=payout.vendor.business_name,
            payout_amount=float(payout.payout_amount),
            payout_period=f"{payout.payout_period_start} to {payout.payout_period_end}",
            payment_reference=payout.payment_reference
        )
    except Exception as e:
        logger.error(f"Failed to send payout processed email: {e}")

    return {
        "message": "Payout marked as paid",
        "payout_id": str(payout.id),
        "status": payout.status,
        "processed_at": payout.processed_at.isoformat(),
        "processed_by": str(current_admin.id),
    }


@router.get("/payouts/{payout_id}/items")
async def get_payout_items(
    payout_id: UUID,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Get payout items

    Requires admin role
    """
    from app.models.payment import PayoutItem

    result = await db.execute(select(PayoutItem).where(PayoutItem.payout_id == payout_id))
    items = result.scalars().all()

    return {
        "payout_id": str(payout_id),
        "items": [
            {
                "id": str(item.id),
                "order_id": str(item.order_id),
                "order_number": item.order.order_number,
                "product_title": item.order_item.product_title,
                "quantity": item.order_item.quantity,
                "item_amount": float(item.item_amount),
                "commission_rate": float(item.commission_rate),
                "commission_amount": float(item.commission_amount),
                "payout_amount": float(item.payout_amount),
            }
            for item in items
        ]
    }


@router.get("/payouts/{payout_id}/history")
async def get_payout_history(
    payout_id: UUID,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Get payout history

    Requires admin role
    """
    from app.models.payment import PayoutHistory

    result = await db.execute(select(PayoutHistory).where(PayoutHistory.payout_id == payout_id))
    history = result.scalars().all()

    return {
        "payout_id": str(payout_id),
        "history": [
            {
                "id": str(entry.id),
                "status": entry.status,
                "notes": entry.notes,
                "created_at": entry.created_at.isoformat() if entry.created_at else None,
                "changed_by": str(entry.changed_by) if entry.changed_by else None,
            }
            for entry in history
        ]
    }


# ==================== ADMIN USER MANAGEMENT ====================

@router.get("/admins")
async def list_admins(
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    List all admin users

    Requires admin role
    """
    result = await db.execute(select(User).where(User.role == UserRole.ADMIN))
    admins = result.scalars().all()

    return {
        "admins": [
            {
                "id": str(admin.id),
                "email": admin.email,
                "full_name": admin.full_name,
                "created_at": admin.created_at.isoformat() if admin.created_at else None,
                "is_active": admin.is_active,
            }
            for admin in admins
        ]
    }


@router.post("/admins")
async def create_admin(
    admin_data: dict,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new admin user

    Requires admin role
    """
    from app.core.security import get_password_hash

    # Only super admin can create admin users
    # TODO: Implement super admin role

    # Check if email already exists
    result = await db.execute(select(User).where(User.email == admin_data.get("email")))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already exists")

    # Create new admin user
    admin = User(
        email=admin_data.get("email"),
        hashed_password=get_password_hash(admin_data.get("password")),
        full_name=admin_data.get("full_name"),
        role=UserRole.ADMIN,
        is_active=True,
        email_verified=True
    )

    db.add(admin)
    await db.commit()

    return {
        "message": "Admin user created successfully",
        "admin_id": str(admin.id)
    }


@router.delete("/admins/{admin_id}")
async def delete_admin(
    admin_id: UUID,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Delete an admin user

    Requires admin role
    """
    # Prevent self-deletion
    if admin_id == current_admin.id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")

    # Get admin
    result = await db.execute(select(User).where(User.id == admin_id))
    admin = result.scalar_one_or_none()

    if not admin:
        raise HTTPException(status_code=404, detail="Admin not found")

    # Delete admin
    await db.delete(admin)
    await db.commit()

    return {
        "message": "Admin deleted successfully",
        "admin_id": str(admin_id)
    }


# ==================== EXPORT ENDPOINTS ====================

@router.get("/export/users")
async def export_users(
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Export all users as CSV

    Requires admin role
    """
    import csv
    from io import StringIO

    # Get all users
    result = await db.execute(select(User))
    users = result.scalars().all()

    # Create CSV
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Name", "Email", "Role", "Active", "Verified", "Created At"])

    for user in users:
        writer.writerow([
            user.id,
            user.full_name,
            user.email,
            user.role.value,
            user.is_active,
            user.email_verified,
            user.created_at
        ])

    # Return as CSV file
    from fastapi.responses import Response
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=users.csv"}
    )


@router.get("/export/orders")
async def export_orders(
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Export all orders as CSV

    Requires admin role
    """
    import csv
    from io import StringIO

    # Get all orders
    result = await db.execute(select(Order))
    orders = result.scalars().all()

    # Create CSV
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["Order ID", "Order Number", "Customer", "Email", "Total", "Status", "Created At"])

    for order in orders:
        writer.writerow([
            order.id,
            order.order_number,
            order.customer.full_name,
            order.customer.email,
            order.total_amount,
            order.fulfillment_status,
            order.created_at
        ])

    # Return as CSV file
    from fastapi.responses import Response
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=orders.csv"}
    )


# ==================== REALTIME UPDATES ====================

@router.websocket("/ws")
async def websocket_endpoint(websocket):
    """
    WebSocket endpoint for realtime updates

    This endpoint allows admin dashboards to subscribe to realtime updates
    about orders, inventory, and other system events.

    Requires admin role
    """
    # TODO: Implement websocket authentication
    await websocket.accept()
    await websocket.send_text("Connected to Shopsoma admin websocket")

    try:
        while True:
            data = await websocket.receive_text()
            # Echo back for now
            await websocket.send_text(f"Message received: {data}")
    except Exception:
        await websocket.close()
