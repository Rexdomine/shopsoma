"""
Create promo_codes table manually
"""
import asyncio
from sqlalchemy import text
from app.core.database import engine

async def create_promo_codes_table():
    async with engine.begin() as conn:
        # Create table if not exists
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS promo_codes (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                code VARCHAR(50) NOT NULL,
                description VARCHAR(500),
                discount_type discounttype NOT NULL,
                discount_value DECIMAL(10, 2) NOT NULL,
                min_purchase_amount DECIMAL(10, 2),
                max_discount_amount DECIMAL(10, 2),
                usage_limit INTEGER,
                usage_count INTEGER NOT NULL DEFAULT 0,
                usage_limit_per_user INTEGER NOT NULL DEFAULT 1,
                valid_from TIMESTAMP WITH TIME ZONE NOT NULL,
                valid_until TIMESTAMP WITH TIME ZONE NOT NULL,
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
            );
        """))

        # Create unique index on code
        await conn.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS ix_promo_codes_code ON promo_codes (code);
        """))

        print("✅ promo_codes table created successfully")

if __name__ == "__main__":
    asyncio.run(create_promo_codes_table())
