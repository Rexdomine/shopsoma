"""Reset vendor password for testing"""
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.models.user import User
from app.core.security import get_password_hash


async def reset_vendor_password():
    """Reset Shopsoma Fashion Store vendor password to 'vendor123'"""
    async with AsyncSessionLocal() as db:
        # Find vendor user
        result = await db.execute(
            select(User).where(User.email == "vendor@shopsoma.com")
        )
        vendor_user = result.scalar_one_or_none()

        if not vendor_user:
            print("❌ Vendor user not found!")
            return

        # Set password to 'vendor123'
        new_password = "vendor123"
        vendor_user.hashed_password = get_password_hash(new_password)

        await db.commit()

        print("✅ Password reset successfully!")
        print(f"\n📧 Email: vendor@shopsoma.com")
        print(f"🔑 Password: {new_password}")
        print(f"👤 Full Name: {vendor_user.full_name}")
        print(f"🏢 Role: {vendor_user.role.value}")


if __name__ == "__main__":
    asyncio.run(reset_vendor_password())
