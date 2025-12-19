"""
Sync phone numbers from addresses to users who don't have phone numbers
"""
import asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import engine, AsyncSessionLocal
from app.models.user import User
from app.models.address import Address

async def sync_phone_numbers():
    async with AsyncSessionLocal() as db:
        # Get all users without phone numbers
        result = await db.execute(
            select(User).where(User.phone_number == None)
        )
        users_without_phone = result.scalars().all()

        print(f"Found {len(users_without_phone)} users without phone numbers")

        updated_count = 0
        for user in users_without_phone:
            # Get the user's first address
            addr_result = await db.execute(
                select(Address)
                .where(Address.user_id == user.id)
                .order_by(Address.created_at.asc())
                .limit(1)
            )
            address = addr_result.scalar_one_or_none()

            if address and address.phone_number:
                user.phone_number = address.phone_number
                updated_count += 1
                print(f"✅ Updated user {user.email} with phone number from address")

        if updated_count > 0:
            await db.commit()
            print(f"\n✅ Successfully updated {updated_count} users with phone numbers")
        else:
            print("\nℹ️  No users needed phone number updates")

if __name__ == "__main__":
    asyncio.run(sync_phone_numbers())
