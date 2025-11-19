"""Seed initial shipping rates"""
import asyncio
from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.models.shipping_rate import ShippingRate
from decimal import Decimal


async def seed_shipping_rates():
    """Seed default shipping rates"""
    async with AsyncSessionLocal() as db:
        # Check if rates already exist
        result = await db.execute(select(ShippingRate))
        existing = result.scalars().first()

        if existing:
            print('✓ Shipping rates already exist')
            return

        # Create default shipping rates
        rates = [
            ShippingRate(
                name='Standard Shipping',
                description='Standard delivery within Nigeria (3-7 business days)',
                base_rate=Decimal('5000.00'),
                country='Nigeria',
                state=None,  # Available for all states
                min_order_value=Decimal('0.00'),
                max_order_value=None,
                min_delivery_days=3,
                max_delivery_days=7,
                is_active=True,
                is_default=True,
                priority=1
            ),
            ShippingRate(
                name='Express Delivery',
                description='Fast delivery within 2-4 business days',
                base_rate=Decimal('8000.00'),
                country='Nigeria',
                state=None,
                min_order_value=Decimal('0.00'),
                max_order_value=None,
                min_delivery_days=2,
                max_delivery_days=4,
                is_active=True,
                is_default=False,
                priority=2
            ),
            ShippingRate(
                name='Lagos Express',
                description='Same-day delivery within Lagos',
                base_rate=Decimal('3000.00'),
                country='Nigeria',
                state='Lagos',
                min_order_value=Decimal('0.00'),
                max_order_value=None,
                min_delivery_days=1,
                max_delivery_days=2,
                is_active=True,
                is_default=False,
                priority=0
            ),
            ShippingRate(
                name='Free Shipping',
                description='Free shipping for orders above ₦100,000',
                base_rate=Decimal('0.00'),
                country='Nigeria',
                state=None,
                min_order_value=Decimal('100000.00'),
                max_order_value=None,
                min_delivery_days=3,
                max_delivery_days=7,
                is_active=True,
                is_default=False,
                priority=3
            ),
        ]

        for rate in rates:
            db.add(rate)

        await db.commit()
        print(f'✓ Created {len(rates)} shipping rates')
        for rate in rates:
            print(f'  - {rate.name}: ₦{rate.base_rate}')


if __name__ == "__main__":
    asyncio.run(seed_shipping_rates())
