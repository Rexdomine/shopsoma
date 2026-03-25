#!/usr/bin/env python3
"""Test script to verify product images and pickup updates in admin order detail"""

import asyncio
import sys
import os

# Add backend to path
sys.path.insert(0, '/Users/rex/Documents/Shopsoma/shopsoma-backend')

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, selectinload
from sqlalchemy import select

from app.models.order import Order, OrderItem
from app.models.product import Product, ProductImage
from app.models.vendor import Vendor
from app.models.vendor_pickup import VendorPickup
from app.models.user import User

# Database URL
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://shopsoma:shopsoma_dev_password@localhost:5432/shopsoma_db')
ASYNC_DATABASE_URL = DATABASE_URL.replace('postgresql://', 'postgresql+asyncpg://')

engine = create_async_engine(ASYNC_DATABASE_URL, echo=False)
async_session_maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def test_order_detail_with_images():
    """Test that order detail query loads product images correctly"""
    print("\n" + "="*80)
    print("TEST 1: Order Detail with Product Images")
    print("="*80)

    async with async_session_maker() as session:
        # Query order with all relationships loaded (same as admin_orders.py)
        order_id = '790ff9e3-5e24-490c-bac2-849200a4ddfe'

        query = select(Order).where(Order.id == order_id).options(
            selectinload(Order.customer),
            selectinload(Order.shipping_address),
            selectinload(Order.billing_address),
            selectinload(Order.items).selectinload(OrderItem.vendor).selectinload(Vendor.user),
            selectinload(Order.items).selectinload(OrderItem.product).selectinload(Product.images),
            selectinload(Order.pickups),
        )

        result = await session.execute(query)
        order = result.scalar_one_or_none()

        if not order:
            print("❌ Order not found")
            return False

        print(f"✅ Order found: {order.order_number}")
        print(f"   Customer: {order.customer.email}")
        print(f"   Items count: {len(order.items)}")
        print(f"   Pickups count: {len(order.pickups)}")

        # Check each item for product images
        for idx, item in enumerate(order.items, 1):
            print(f"\n   Item {idx}: {item.product.title}")
            print(f"   - Product ID: {item.product_id}")
            print(f"   - Has product relationship: {hasattr(item, 'product') and item.product is not None}")

            if hasattr(item, 'product') and item.product:
                print(f"   - Product images count: {len(item.product.images)}")

                if item.product.images:
                    # Apply same logic as backend
                    primary_img = next((img for img in item.product.images if img.is_primary), None)
                    first_img = item.product.images[0] if item.product.images else None

                    selected_img = primary_img or first_img

                    if selected_img:
                        product_image_url = selected_img.thumbnail_url or selected_img.image_url
                        print(f"   - ✅ Product image URL: {product_image_url}")
                        print(f"   - Is primary: {selected_img.is_primary}")
                        print(f"   - Has thumbnail: {selected_img.thumbnail_url is not None}")
                    else:
                        print(f"   - ⚠️  No images found for product")
                else:
                    print(f"   - ⚠️  Product has no images")

        return True


async def test_pickup_data():
    """Test that pickup data is loaded correctly"""
    print("\n" + "="*80)
    print("TEST 2: Pickup Data Loading")
    print("="*80)

    async with async_session_maker() as session:
        order_id = '790ff9e3-5e24-490c-bac2-849200a4ddfe'

        query = select(Order).where(Order.id == order_id).options(
            selectinload(Order.pickups)
        )

        result = await session.execute(query)
        order = result.scalar_one_or_none()

        if not order:
            print("❌ Order not found")
            return False

        print(f"✅ Order: {order.order_number}")
        print(f"   Pickups count: {len(order.pickups)}")

        for idx, pickup in enumerate(order.pickups, 1):
            print(f"\n   Pickup {idx}:")
            print(f"   - ID: {pickup.id}")
            print(f"   - Status: {pickup.status}")
            print(f"   - Scheduled pickup date: {pickup.scheduled_pickup_date or 'Not set'}")
            print(f"   - Actual pickup date: {pickup.actual_pickup_date or 'Not set'}")
            print(f"   - Logistics partner: {pickup.logistics_partner or 'Not set'}")
            print(f"   - Tracking number: {pickup.tracking_number or 'Not set'}")
            print(f"   - QC notes: {pickup.qc_notes or 'Not set'}")
            print(f"   - Admin notes: {pickup.admin_notes or 'Not set'}")

        return True


async def main():
    """Run all tests"""
    try:
        test1_passed = await test_order_detail_with_images()
        test2_passed = await test_pickup_data()

        print("\n" + "="*80)
        print("TEST SUMMARY")
        print("="*80)
        print(f"Product Images Test: {'✅ PASSED' if test1_passed else '❌ FAILED'}")
        print(f"Pickup Data Test: {'✅ PASSED' if test2_passed else '❌ FAILED'}")

        if test1_passed and test2_passed:
            print("\n✅ All tests passed! Backend is loading data correctly.")
        else:
            print("\n❌ Some tests failed.")

    finally:
        await engine.dispose()


if __name__ == '__main__':
    asyncio.run(main())
