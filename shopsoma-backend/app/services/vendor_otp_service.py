"""Vendor OTP Service for activation flow"""
import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from passlib.context import CryptContext

from app.models import VendorOTP, Vendor
from app.services.email_service import email_service


# Password context for hashing OTP codes
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class VendorOTPService:
    """Service for vendor OTP operations"""

    OTP_LENGTH = 6
    OTP_EXPIRY_MINUTES = 15
    MAX_ATTEMPTS = 5

    @staticmethod
    def generate_otp_code(length: int = OTP_LENGTH) -> str:
        """Generate a random numeric OTP code"""
        return ''.join(secrets.choice(string.digits) for _ in range(length))

    @staticmethod
    def hash_code(code: str) -> str:
        """Hash OTP code before storage"""
        return pwd_context.hash(code)

    @staticmethod
    def verify_code(plain_code: str, hashed_code: str) -> bool:
        """Verify OTP code against hash"""
        return pwd_context.verify(plain_code, hashed_code)

    @staticmethod
    async def create_and_send_otp(
        db: AsyncSession,
        vendor_id: str,
        email: str
    ) -> VendorOTP:
        """
        Create a new OTP for vendor activation and send via email.
        Invalidates any previous unused OTPs for this vendor.
        """
        # Invalidate any existing unused OTPs for this vendor
        await db.execute(
            VendorOTP.__table__.update()
            .where(
                and_(
                    VendorOTP.vendor_id == vendor_id,
                    VendorOTP.is_used == False
                )
            )
            .values(is_used=True)
        )

        # Generate new OTP code
        plain_code = VendorOTPService.generate_otp_code()
        code_hash = VendorOTPService.hash_code(plain_code)

        # Calculate expiration
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=VendorOTPService.OTP_EXPIRY_MINUTES)

        # Create OTP record
        otp = VendorOTP(
            vendor_id=vendor_id,
            email=email,
            code_hash=code_hash,
            expires_at=expires_at,
            attempts=0,
            max_attempts=VendorOTPService.MAX_ATTEMPTS,
            is_used=False
        )

        db.add(otp)
        await db.commit()
        await db.refresh(otp)

        # Send OTP via email
        try:
            await email_service.send_vendor_otp_email(
                email=email,
                otp_code=plain_code,
                expiry_minutes=VendorOTPService.OTP_EXPIRY_MINUTES
            )
        except Exception as e:
            # Log error but don't fail - OTP was created
            print(f"Failed to send OTP email to {email}: {e}")

        return otp

    @staticmethod
    async def verify_otp(
        db: AsyncSession,
        email: str,
        plain_code: str
    ) -> tuple[bool, str, Optional[VendorOTP]]:
        """
        Verify OTP code for vendor activation.
        Returns: (success: bool, message: str, otp: Optional[VendorOTP])
        """
        # Find the most recent unused OTP for this email
        result = await db.execute(
            select(VendorOTP)
            .where(
                and_(
                    VendorOTP.email == email,
                    VendorOTP.is_used == False
                )
            )
            .order_by(VendorOTP.created_at.desc())
            .limit(1)
        )
        otp = result.scalar_one_or_none()

        if not otp:
            return False, "No active verification code found. Please request a new one.", None

        # Check if OTP is expired
        if otp.is_expired():
            return False, "Verification code has expired. Please request a new one.", otp

        # Check if OTP is locked due to too many attempts
        if otp.is_locked():
            return False, "Too many failed attempts. Please request a new code.", otp

        # Increment attempt counter
        otp.attempts += 1
        await db.commit()

        # Verify the code
        if not VendorOTPService.verify_code(plain_code, otp.code_hash):
            remaining_attempts = otp.max_attempts - otp.attempts
            if remaining_attempts > 0:
                return False, f"Invalid code. {remaining_attempts} attempts remaining.", otp
            else:
                return False, "Invalid code. Too many failed attempts. Please request a new code.", otp

        # Success - mark as used
        otp.is_used = True
        otp.verified_at = datetime.now(timezone.utc)
        await db.commit()

        return True, "Verification successful!", otp

    @staticmethod
    async def get_latest_otp(
        db: AsyncSession,
        email: str
    ) -> Optional[VendorOTP]:
        """Get the latest OTP for an email"""
        result = await db.execute(
            select(VendorOTP)
            .where(VendorOTP.email == email)
            .order_by(VendorOTP.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    def mask_email(email: str) -> str:
        """Mask email for display (e.g., j***@example.com)"""
        if '@' not in email:
            return email

        local, domain = email.split('@', 1)
        if len(local) <= 2:
            masked_local = local[0] + '***'
        else:
            masked_local = local[0] + '***' + local[-1]

        return f"{masked_local}@{domain}"
