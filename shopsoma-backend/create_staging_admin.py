"""
Create an admin user on Render staging database
Run this script locally but it will connect to Render's PostgreSQL
"""
import asyncio
import os
import sys
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select

# Add project root to path
sys.path.insert(0, os.path.dirname(__file__))

from app.models.user import User, UserRole
from app.core.security import get_password_hash


async def create_staging_admin():
    """Create an admin user on staging database"""

    # Get staging DATABASE_URL from user input
    print("\n" + "="*70)
    print("CREATE STAGING ADMIN USER")
    print("="*70)
    print("\nThis script will create an admin user on your Render staging database.")
    print("\n📋 To get your Render DATABASE_URL:")
    print("   1. Go to https://dashboard.render.com/")
    print("   2. Select your 'shopsoma-staging-db' database")
    print("   3. Scroll down to 'Connections'")
    print("   4. Copy the 'External Database URL'")
    print("   5. Paste it below")
    print("\n⚠️  Important: Use the EXTERNAL DATABASE URL, not the internal one")
    print("-"*70)

    staging_db_url = input("\nPaste your Render DATABASE_URL here: ").strip()

    if not staging_db_url:
        print("❌ Error: DATABASE_URL cannot be empty")
        return

    # Convert to async URL if needed
    if staging_db_url.startswith("postgresql://"):
        async_db_url = staging_db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif staging_db_url.startswith("postgres://"):
        async_db_url = staging_db_url.replace("postgres://", "postgresql+asyncpg://", 1)
    else:
        async_db_url = staging_db_url

    print(f"\n🔌 Connecting to staging database...")

    try:
        # Create async engine
        engine = create_async_engine(
            async_db_url,
            echo=False,
            pool_pre_ping=True,
        )

        # Create session factory
        AsyncSessionLocal = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        # Create admin user
        async with AsyncSessionLocal() as db:
            # Check if admin already exists
            result = await db.execute(
                select(User).where(User.email == 'admin@shopsoma.com')
            )
            existing_admin = result.scalar_one_or_none()

            if existing_admin:
                print(f"\n✅ Admin user already exists on staging!")
                print(f"   Email: admin@shopsoma.com")
                print(f"   Name: {existing_admin.full_name}")
                print(f"   Role: {existing_admin.role.value}")
                print(f"   Active: {existing_admin.is_active}")
                print(f"\n   Use password: Admin123!Staging")
                return

            # Create admin user with strong staging password
            admin_user = User(
                email='admin@shopsoma.com',
                hashed_password=get_password_hash('Admin123!Staging'),
                full_name='Shopsoma Admin',
                role=UserRole.ADMIN,
                is_active=True,
                email_verified=True
            )

            db.add(admin_user)
            await db.commit()
            await db.refresh(admin_user)

            print("\n" + "="*70)
            print("🎉 STAGING ADMIN USER CREATED SUCCESSFULLY!")
            print("="*70)
            print(f"\n📧 Email:    admin@shopsoma.com")
            print(f"🔑 Password: Admin123!Staging")
            print(f"👤 Name:     {admin_user.full_name}")
            print(f"🎭 Role:     {admin_user.role.value}")
            print(f"\n🌐 Login at: https://shopsoma-staging.onrender.com/login")
            print(f"⚙️  Admin Panel: https://shopsoma-staging.onrender.com/admin")
            print("\n" + "="*70)
            print("⚠️  IMPORTANT: Save these credentials securely!")
            print("="*70 + "\n")

        await engine.dispose()

    except Exception as e:
        print(f"\n❌ Error connecting to database:")
        print(f"   {str(e)}")
        print(f"\n💡 Troubleshooting:")
        print(f"   - Make sure you copied the EXTERNAL DATABASE URL")
        print(f"   - Check that your IP is allowed in Render's firewall settings")
        print(f"   - Verify the URL starts with postgresql:// or postgres://")
        sys.exit(1)


if __name__ == '__main__':
    asyncio.run(create_staging_admin())
