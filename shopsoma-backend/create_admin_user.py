"""
Create an admin user for testing the admin panel
"""
import asyncio
from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.models.user import User, UserRole
from app.core.security import get_password_hash


async def create_admin_user():
    """Create an admin user for testing"""
    async with AsyncSessionLocal() as db:
        # Check if admin already exists
        result = await db.execute(
            select(User).where(User.email == 'admin@shopsoma.com')
        )
        existing_admin = result.scalar_one_or_none()

        if existing_admin:
            print(f"✅ Admin user already exists: admin@shopsoma.com")
            print(f"   Name: {existing_admin.full_name}")
            print(f"   Role: {existing_admin.role.value}")
            print(f"   Active: {existing_admin.is_active}")
            return

        # Create admin user
        admin_user = User(
            email='admin@shopsoma.com',
            hashed_password=get_password_hash('Admin123'),  # Password: Admin123
            full_name='Admin User',
            role=UserRole.ADMIN,
            is_active=True,
            email_verified=True
        )

        db.add(admin_user)
        await db.commit()
        await db.refresh(admin_user)

        print("\n🎉 Admin user created successfully!")
        print(f"   Email: admin@shopsoma.com")
        print(f"   Password: Admin123")
        print(f"   Name: {admin_user.full_name}")
        print(f"   Role: {admin_user.role.value}")
        print(f"\n   You can now login with these credentials at http://localhost:5173/login")
        print(f"   Then navigate to http://localhost:5173/admin/users to manage users")


if __name__ == '__main__':
    asyncio.run(create_admin_user())
