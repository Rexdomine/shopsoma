"""Create a test OTP with known code for testing"""
import asyncio
from datetime import datetime, timedelta, timezone
from app.core.database import AsyncSessionLocal
from app.models import VendorOTP, Vendor, User
from app.services.vendor_otp_service import VendorOTPService
from sqlalchemy import select

async def create_test_otp():
    async with AsyncSessionLocal() as db:
        # Find vendor by email
        result = await db.execute(
            select(User).where(User.email == "dominusparte@gmail.com")
        )
        user = result.scalar_one_or_none()

        if not user:
            print("❌ User not found")
            return

        vendor_result = await db.execute(
            select(Vendor).where(Vendor.user_id == user.id)
        )
        vendor = vendor_result.scalar_one_or_none()

        if not vendor:
            print("❌ Vendor not found")
            return

        # Delete existing OTPs
        await db.execute(
            VendorOTP.__table__.delete().where(VendorOTP.email == "dominusparte@gmail.com")
        )

        # Create OTP with known code "123456"
        test_code = "123456"
        code_hash = VendorOTPService.hash_code(test_code)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=30)

        otp = VendorOTP(
            vendor_id=str(vendor.id),
            email=user.email,
            code_hash=code_hash,
            expires_at=expires_at,
            attempts=0,
            max_attempts=5,
            is_used=False
        )

        db.add(otp)
        await db.commit()

        print(f"✅ Created test OTP for {user.email}")
        print(f"   Code: {test_code}")
        print(f"   Expires at: {expires_at}")

if __name__ == "__main__":
    asyncio.run(create_test_otp())
