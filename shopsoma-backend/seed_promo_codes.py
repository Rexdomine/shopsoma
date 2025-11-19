"""Seed promo codes for testing"""
import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import AsyncSessionLocal
from app.models.promo_code import PromoCode, DiscountType


async def seed_promo_codes():
    """Seed initial promo codes"""
    async with AsyncSessionLocal() as session:
        # Check if promo codes already exist
        result = await session.execute(select(PromoCode))
        existing_codes = result.scalars().all()
        count = len(existing_codes)

        if count > 0:
            print(f"✓ Promo codes already exist ({count} codes)")
            return

        promo_codes = [
            {
                "code": "WELCOME10",
                "description": "10% off for new customers",
                "discount_type": DiscountType.PERCENTAGE,
                "discount_value": Decimal("10.00"),
                "min_purchase_amount": Decimal("50000.00"),  # ₦50,000 minimum
                "max_discount_amount": Decimal("20000.00"),  # Max ₦20,000 discount
                "usage_limit": 100,
                "usage_limit_per_user": 1,
                "valid_from": datetime.now(),
                "valid_until": datetime.now() + timedelta(days=90),
                "is_active": True,
            },
            {
                "code": "SAVE20",
                "description": "20% off for orders above ₦100,000",
                "discount_type": DiscountType.PERCENTAGE,
                "discount_value": Decimal("20.00"),
                "min_purchase_amount": Decimal("100000.00"),
                "max_discount_amount": Decimal("50000.00"),
                "usage_limit": 50,
                "usage_limit_per_user": 1,
                "valid_from": datetime.now(),
                "valid_until": datetime.now() + timedelta(days=60),
                "is_active": True,
            },
            {
                "code": "FREESHIP",
                "description": "Free shipping on orders above ₦75,000",
                "discount_type": DiscountType.FIXED_AMOUNT,
                "discount_value": Decimal("5000.00"),  # Covers most shipping
                "min_purchase_amount": Decimal("75000.00"),
                "max_discount_amount": None,
                "usage_limit": None,  # Unlimited
                "usage_limit_per_user": 5,
                "valid_from": datetime.now(),
                "valid_until": datetime.now() + timedelta(days=180),
                "is_active": True,
            },
            {
                "code": "FLASH50",
                "description": "₦50,000 off flash sale",
                "discount_type": DiscountType.FIXED_AMOUNT,
                "discount_value": Decimal("50000.00"),
                "min_purchase_amount": Decimal("200000.00"),
                "max_discount_amount": None,
                "usage_limit": 20,
                "usage_limit_per_user": 1,
                "valid_from": datetime.now(),
                "valid_until": datetime.now() + timedelta(days=7),
                "is_active": True,
            },
        ]

        for promo_data in promo_codes:
            promo = PromoCode(**promo_data)
            session.add(promo)

        await session.commit()
        print(f"✓ Seeded {len(promo_codes)} promo codes")

        # Print codes for reference
        print("\nTest Promo Codes:")
        print("-" * 60)
        for code in promo_codes:
            print(f"  {code['code']}: {code['description']}")


if __name__ == "__main__":
    asyncio.run(seed_promo_codes())
