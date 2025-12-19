"""
API endpoints for Vendor Applications
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from uuid import UUID

from app.core.database import get_db
from app.api.dependencies import get_current_active_user, get_current_admin
from app.models.user import User
from app.schemas.vendor_application import (
    VendorApplicationCreate,
    VendorApplicationResponse,
    VendorApplicationApproval
)
from app.services.vendor_application_service import VendorApplicationService

router = APIRouter()


@router.post("/", response_model=VendorApplicationResponse, status_code=status.HTTP_201_CREATED)
async def create_vendor_application(
    application: VendorApplicationCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new vendor application (public endpoint)
    """
    try:
        new_application = await VendorApplicationService.create_application(db, application)
        return new_application
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        print(f"Error creating application: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create application: {str(e)}"
        )


@router.get("/{application_id}", response_model=VendorApplicationResponse)
async def get_vendor_application(
    application_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """
    Get vendor application by ID (admin only)
    """
    application = await VendorApplicationService.get_application_by_id(db, application_id)
    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found"
        )
    return application


@router.get("/", response_model=List[VendorApplicationResponse])
async def list_vendor_applications(
    status: str = "pending_review",
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """
    List vendor applications by status (admin only)
    """
    applications = await VendorApplicationService.get_applications_by_status(
        db, status, skip, limit
    )
    return applications


@router.post("/{application_id}/approve", response_model=VendorApplicationResponse)
async def approve_vendor_application(
    application_id: UUID,
    approval_data: VendorApplicationApproval,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """
    Approve vendor application and trigger activation flow (admin only)
    """
    if approval_data.status != "approved":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Use this endpoint only for approval. Use /reject for rejection."
        )

    try:
        approved_application = await VendorApplicationService.approve_application(
            db=db,
            application_id=application_id,
            admin_user_id=current_user.id,
            admin_notes=approval_data.admin_notes
        )
        return approved_application
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        print(f"Approval error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to approve application: {str(e)}"
        )


@router.post("/{application_id}/reject", response_model=VendorApplicationResponse)
async def reject_vendor_application(
    application_id: UUID,
    approval_data: VendorApplicationApproval,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """
    Reject vendor application (admin only)
    """
    if approval_data.status != "rejected":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Use this endpoint only for rejection. Use /approve for approval."
        )

    try:
        rejected_application = await VendorApplicationService.reject_application(
            db=db,
            application_id=application_id,
            admin_user_id=current_user.id,
            admin_notes=approval_data.admin_notes
        )
        return rejected_application
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to reject application"
        )


@router.delete("/{application_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_vendor_application(
    application_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """
    Delete vendor application (admin only - for testing/cleanup purposes)
    """
    try:
        application = await VendorApplicationService.get_application_by_id(db, application_id)
        if not application:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Application not found"
            )

        # Delete the application
        await db.delete(application)
        await db.commit()

        return None
    except HTTPException:
        raise
    except Exception as e:
        print(f"Delete error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete application"
        )
