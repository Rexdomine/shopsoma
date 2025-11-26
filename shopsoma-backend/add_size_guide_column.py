"""
Add size_guide column to products table
"""
import asyncio
from sqlalchemy import text
from app.core.database import engine

async def add_size_guide_column():
    async with engine.begin() as conn:
        # Check if column exists
        result = await conn.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name='products' AND column_name='size_guide';
        """))

        if result.fetchone() is None:
            # Column doesn't exist, add it
            await conn.execute(text("""
                ALTER TABLE products
                ADD COLUMN size_guide JSONB;
            """))
            print("✅ size_guide column added successfully")
        else:
            print("ℹ️  size_guide column already exists")

if __name__ == "__main__":
    asyncio.run(add_size_guide_column())
