"""Reset admin password to Admin123"""
import asyncio
from sqlalchemy import select, update
from app.core.database import AsyncSessionLocal
from app.core.config import settings
from app.models.user import User
from app.core.security import get_password_hash


async def reset_admin_password():
    """Reset admin password"""
    admin_email = getattr(settings, 'ADMIN_EMAIL', 'kayodedevelopment@gmail.com')
    async with AsyncSessionLocal() as db:
        # Update admin password
        await db.execute(
            update(User)
            .where(User.email == admin_email)
            .values(hashed_password=get_password_hash('Admin123'))
        )
        await db.commit()

        print("Admin password reset successfully!")
        print(f"   Email: {admin_email}")
        print("   Password: Admin123")


if __name__ == '__main__':
    asyncio.run(reset_admin_password())
