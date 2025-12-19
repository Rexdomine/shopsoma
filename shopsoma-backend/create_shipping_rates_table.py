"""
Create shipping_rates table manually
"""
import asyncio
from sqlalchemy import text
from app.core.database import engine

async def create_shipping_rates_table():
    async with engine.begin() as conn:
        # Create table if not exists
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS shipping_rates (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                name VARCHAR(100) NOT NULL,
                description VARCHAR(500),
                base_rate DECIMAL(10, 2) NOT NULL,
                country VARCHAR(100) NOT NULL,
                state VARCHAR(100),
                min_order_value DECIMAL(10, 2),
                max_order_value DECIMAL(10, 2),
                min_delivery_days INTEGER NOT NULL,
                max_delivery_days INTEGER NOT NULL,
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                is_default BOOLEAN NOT NULL DEFAULT FALSE,
                priority INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
            );
        """))

        print("✅ shipping_rates table created successfully")

if __name__ == "__main__":
    asyncio.run(create_shipping_rates_table())
