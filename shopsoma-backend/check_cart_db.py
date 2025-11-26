#!/usr/bin/env python3
"""
Quick script to check what's actually in the cart_items table
"""
import asyncio
from sqlalchemy import select, text
from app.core.database import get_async_session
from app.models.cart import CartItem

async def check_cart():
    async for session in get_async_session():
        # Check all cart items
        result = await session.execute(
            select(CartItem.id, CartItem.user_id, CartItem.session_id, CartItem.quantity, CartItem.created_at)
            .order_by(CartItem.created_at.desc())
            .limit(20)
        )
        items = result.all()

        print(f"\n=== ALL CART ITEMS (latest 20) ===")
        for item in items:
            print(f"ID: {item.id}")
            print(f"  user_id: {item.user_id}")
            print(f"  session_id: {item.session_id}")
            print(f"  quantity: {item.quantity}")
            print(f"  created_at: {item.created_at}")
            print()

        # Count by type
        guest_count = await session.execute(
            text("SELECT COUNT(*) FROM cart_items WHERE user_id IS NULL")
        )
        user_count = await session.execute(
            text("SELECT COUNT(*) FROM cart_items WHERE user_id IS NOT NULL")
        )

        print(f"=== SUMMARY ===")
        print(f"Guest cart items (user_id IS NULL): {guest_count.scalar()}")
        print(f"User cart items (user_id IS NOT NULL): {user_count.scalar()}")
        print()

        break

if __name__ == "__main__":
    asyncio.run(check_cart())
