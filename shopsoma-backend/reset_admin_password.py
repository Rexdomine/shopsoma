"""Reset admin password to Admin123"""
import asyncio
from sqlalchemy import select, update
from app.core.database import AsyncSessionLocal
from app.models.user import User
from app.core.security import get_password_hash


async def reset_admin_password():
    """Reset admin password"""
    async with AsyncSessionLocal() as db:
        # Update admin password
        await db.execute(
            update(User)
            .where(User.email == 'admin@shopsoma.com')
            .values(hashed_password=get_password_hash('Admin123'))
        )
        await db.commit()

        print("✅ Admin password reset successfully!")
        print("   Email: admin@shopsoma.com")
        print("   Password: Admin123")


if __name__ == '__main__':
    asyncio.run(reset_admin_password())
