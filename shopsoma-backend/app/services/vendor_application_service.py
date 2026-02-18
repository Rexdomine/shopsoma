"""
Service layer for Vendor Applications
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from typing import Optional, List
from uuid import UUID
from datetime import datetime

from app.models.vendor_application import VendorApplication
from app.models.vendor import Vendor, KYCStatus
from app.models.user import User, UserRole
from app.schemas.vendor_application import VendorApplicationCreate, VendorApplicationApproval
from app.services.vendor_otp_service import VendorOTPService
from app.services.email_service import EmailService


class VendorApplicationService:
    """Service for handling vendor applications"""

    @staticmethod
    async def create_application(
        db: AsyncSession,
        application_data: VendorApplicationCreate
    ) -> VendorApplication:
        """Create a new vendor application"""
        # Check if email already exists in applications
        existing_app = await db.execute(
            select(VendorApplication).where(VendorApplication.email == application_data.email)
        )
        if existing_app.scalar_one_or_none():
            raise ValueError("An application with this email already exists")

        # Check if email exists in active vendors
        existing_vendor = await db.execute(
            select(Vendor).join(User, Vendor.user_id == User.id).where(User.email == application_data.email)
        )
        if existing_vendor.scalar_one_or_none():
            raise ValueError("A vendor with this email already exists")

        # Create application
        application = VendorApplication(
            first_name=application_data.first_name,
            last_name=application_data.last_name,
            email=application_data.email,
            phone_country_code=application_data.phone_country_code,
            phone_number=application_data.phone_number,
            business_name=application_data.business_name,
            business_location=application_data.business_location,
            is_business_registered=application_data.is_business_registered,
            product_categories=application_data.product_categories,
            local_production_level=application_data.local_production_level,
            years_in_business=application_data.years_in_business,
            brand_story=application_data.brand_story,
            website_link=application_data.website_link,
            social_media_handles=application_data.social_media_handles.model_dump() if application_data.social_media_handles else None,
            status="pending_review"
        )

        db.add(application)
        await db.commit()
        await db.refresh(application)

        # Send confirmation email to applicant
        try:
            email_service = EmailService()
            await email_service.send_vendor_application_confirmation(
                email=application.email,
                first_name=application.first_name,
                business_name=application.business_name
            )
        except Exception as e:
            # Log error but don't fail the application creation
            print(f"Failed to send application confirmation email: {e}")

        return application

    @staticmethod
    async def get_application_by_id(
        db: AsyncSession,
        application_id: UUID
    ) -> Optional[VendorApplication]:
        """Get application by ID"""
        result = await db.execute(
            select(VendorApplication).where(VendorApplication.id == application_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_applications_by_status(
        db: AsyncSession,
        status: str,
        skip: int = 0,
        limit: int = 100
    ) -> List[VendorApplication]:
        """Get applications by status"""
        result = await db.execute(
            select(VendorApplication)
            .where(VendorApplication.status == status)
            .offset(skip)
            .limit(limit)
            .order_by(VendorApplication.created_at.desc())
        )
        return result.scalars().all()

    @staticmethod
    async def approve_application(
        db: AsyncSession,
        application_id: UUID,
        admin_user_id: UUID,
        admin_notes: Optional[str] = None
    ) -> VendorApplication:
        """
        Approve vendor application and trigger activation flow
        """
        # Get application
        application = await VendorApplicationService.get_application_by_id(db, application_id)
        if not application:
            raise ValueError("Application not found")

        if application.status == "approved":
            raise ValueError("Application already approved")

        # Create or reuse User account for vendor
        from app.core.security import get_password_hash
        import secrets

        existing_user_result = await db.execute(
            select(User).where(User.email == application.email)
        )
        existing_user = existing_user_result.scalar_one_or_none()

        if existing_user and existing_user.vendor:
            raise ValueError("A vendor with this email already exists")

        if existing_user:
            new_user = existing_user
            new_user.full_name = f"{application.first_name} {application.last_name}"
            new_user.phone_number = f"{application.phone_country_code}{application.phone_number}"
            if new_user.role != UserRole.VENDOR:
                new_user.role = UserRole.VENDOR
        else:
            temp_password = secrets.token_urlsafe(32)
            new_user = User(
                full_name=f"{application.first_name} {application.last_name}",
                email=application.email,
                phone_number=f"{application.phone_country_code}{application.phone_number}",
                hashed_password=get_password_hash(temp_password),
                role=UserRole.VENDOR,
                is_active=False  # Will be activated after OTP verification
            )
            db.add(new_user)
            await db.flush()

        # Create Vendor profile
        vendor = Vendor(
            user_id=new_user.id,
            business_name=application.business_name,
            business_description=application.brand_story or "",
            business_address=application.business_location,
            business_phone=f"{application.phone_country_code}{application.phone_number}",
            kyc_status=KYCStatus.PENDING,
            approved=True,  # Approved by admin, vendor can now activate their account
            is_onboarding=True,
            brand_info_completed=False,
            payout_info_completed=False
        )
        db.add(vendor)
        await db.flush()

        # Update application
        application.status = "approved"
        application.vendor_id = vendor.id
        application.reviewed_by = admin_user_id
        application.reviewed_at = datetime.utcnow()
        application.admin_notes = admin_notes

        await db.commit()
        await db.refresh(application)

        # Generate OTP and send activation email
        try:
            await VendorOTPService.create_and_send_otp(
                db=db,
                vendor_id=vendor.id,
                email=application.email
            )
        except Exception as e:
            # Log error but don't fail the approval
            print(f"Failed to send activation email: {e}")

        return application

    @staticmethod
    async def reject_application(
        db: AsyncSession,
        application_id: UUID,
        admin_user_id: UUID,
        admin_notes: Optional[str] = None
    ) -> VendorApplication:
        """Reject vendor application"""
        application = await VendorApplicationService.get_application_by_id(db, application_id)
        if not application:
            raise ValueError("Application not found")

        if application.status == "rejected":
            raise ValueError("Application already rejected")

        application.status = "rejected"
        application.reviewed_by = admin_user_id
        application.reviewed_at = datetime.utcnow()
        application.admin_notes = admin_notes

        await db.commit()
        await db.refresh(application)

        # Send rejection email to applicant
        try:
            email_service = EmailService()
            await email_service.send_vendor_application_rejection(
                email=application.email,
                first_name=application.first_name,
                business_name=application.business_name,
                reason=admin_notes
            )
        except Exception as e:
            # Log error but don't fail the rejection
            print(f"Failed to send rejection email: {e}")

        return application
