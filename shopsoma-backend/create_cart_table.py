"""
Create cart_items table manually
"""
import asyncio
from sqlalchemy import text
from app.core.database import engine

async def create_cart_items_table():
    async with engine.begin() as conn:
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS cart_items (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                session_id VARCHAR(255),
                product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
                variant_id UUID REFERENCES product_variants(id) ON DELETE CASCADE,
                quantity INTEGER NOT NULL DEFAULT 1,
                price DECIMAL(10, 2) NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """))
        print("✅ cart_items table created successfully")

if __name__ == "__main__":
    asyncio.run(create_cart_items_table())
