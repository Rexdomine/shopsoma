"""
Add date_of_birth and gender columns to users table
"""
import asyncio
from sqlalchemy import text
from app.core.database import engine

async def add_user_profile_fields():
    async with engine.begin() as conn:
        # Check if date_of_birth column exists
        result = await conn.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name='users' AND column_name='date_of_birth';
        """))

        if result.fetchone() is None:
            # Column doesn't exist, add it
            await conn.execute(text("""
                ALTER TABLE users
                ADD COLUMN date_of_birth DATE;
            """))
            print("✅ date_of_birth column added successfully")
        else:
            print("ℹ️  date_of_birth column already exists")

        # Check if gender column exists
        result = await conn.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name='users' AND column_name='gender';
        """))

        if result.fetchone() is None:
            # Column doesn't exist, add it
            await conn.execute(text("""
                ALTER TABLE users
                ADD COLUMN gender VARCHAR(50);
            """))
            print("✅ gender column added successfully")
        else:
            print("ℹ️  gender column already exists")

if __name__ == "__main__":
    asyncio.run(add_user_profile_fields())
