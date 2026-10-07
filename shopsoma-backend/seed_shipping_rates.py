"""Seed initial shipping rates"""
import asyncio
import sys
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Ensure UTF-8 output on Windows terminal
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from app.core.database import AsyncSessionLocal
from app.models.shipping_rate import ShippingRate


def get_default_shipping_rates():
    return [
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


async def ensure_default_shipping_rates(db: AsyncSession) -> bool:
    """Ensure default shipping rates exist in the database. Returns True if seeded, False if already present."""
    result = await db.execute(select(ShippingRate.id).limit(1))
    existing = result.scalar_one_or_none()

    if existing:
        return False

    rates = get_default_shipping_rates()
    for rate in rates:
        db.add(rate)

    await db.commit()
    return True


async def seed_shipping_rates():
    """Seed default shipping rates"""
    async with AsyncSessionLocal() as db:
        created = await ensure_default_shipping_rates(db)
        if not created:
            print("[INFO] Shipping rates already exist")
            return

        rates = get_default_shipping_rates()
        print(f"[SUCCESS] Created {len(rates)} shipping rates")
        for rate in rates:
            print(f"  - {rate.name}: ₦{rate.base_rate}")


if __name__ == "__main__":
    asyncio.run(seed_shipping_rates())

