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
    from app.models.vendor_application import VendorApplication

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
    from datetime import datetime
    
    result = await db.execute(
        select(Vendor).where(Vendor.id == vendor_id)
    )
    vendor = result.scalar_one_or_none()
    
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")
    
    if vendor.approved:
        raise HTTPException(status_code=400, detail="Vendor already approved")
    
    vendor.approved = True
    vendor.approved_at = datetime.utcnow()
    vendor.approved_by = current_admin.id
    
    await db.commit()
    await db.refresh(vendor)
    
    return {
        "message": "Vendor approved successfully",
        "vendor_id": str(vendor.id),
        "approved": vendor.approved,
        "approved_at": vendor.approved_at.isoformat()
    }


@router.put("/vendors/{vendor_id}/kyc/approve")
async def approve_vendor_kyc(
    vendor_id: UUID,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Approve vendor KYC documents
    
    Requires admin role
    """
    from datetime import datetime
    
    result = await db.execute(
        select(Vendor).where(Vendor.id == vendor_id)
    )
    vendor = result.scalar_one_or_none()
    
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")
    
    if vendor.kyc_status != KYCStatus.SUBMITTED:
        raise HTTPException(status_code=400, detail="KYC must be submitted before approval")
    
    vendor.kyc_status = KYCStatus.APPROVED
    vendor.kyc_reviewed_at = datetime.utcnow()
    
    await db.commit()
    await db.refresh(vendor)
    
    return {
        "message": "KYC approved successfully",
        "vendor_id": str(vendor.id),
        "kyc_status": vendor.kyc_status.value,
        "kyc_reviewed_at": vendor.kyc_reviewed_at.isoformat()
    }


@router.put("/vendors/{vendor_id}/kyc/reject")
async def reject_vendor_kyc(
    vendor_id: UUID,
    reason: str = Query(..., description="Reason for KYC rejection"),
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Reject vendor KYC documents
    
    Requires admin role
    """
    from datetime import datetime
    
    result = await db.execute(
        select(Vendor).where(Vendor.id == vendor_id)
    )
    vendor = result.scalar_one_or_none()
    
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")
    
    if vendor.kyc_status not in [KYCStatus.SUBMITTED, KYCStatus.APPROVED]:
        raise HTTPException(status_code=400, detail="Cannot reject KYC with current status")
    
    vendor.kyc_status = KYCStatus.REJECTED
    vendor.kyc_reviewed_at = datetime.utcnow()
    # Note: You may want to add a kyc_rejection_reason field to the Vendor model
    
    await db.commit()
    await db.refresh(vendor)
    
    return {
        "message": "KYC rejected successfully",
        "vendor_id": str(vendor.id),
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
