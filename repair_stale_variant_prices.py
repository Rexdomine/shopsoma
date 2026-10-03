#!/usr/bin/env python3
"""
Repair stale ProductVariant prices and set inherits_price for single products.

Finds all products without variations where variant prices do not match product.base_price,
and updates them to match base_price with inherits_price=True.

Usage:
    python repair_stale_variant_prices.py --dry-run
    python repair_stale_variant_prices.py --apply
"""
import argparse
import asyncio
import sys
import os

# Add backend directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'shopsoma-backend'))

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.core.database import get_async_session
from app.models.product import Product, ProductVariant, Variation


async def repair_prices(apply: bool = False):
    print(f"=== Starting Product Price Repair (apply={apply}) ===\n")

    async for db in get_async_session():
        try:
            # Fetch all products with variants and variations
            result = await db.execute(
                select(Product).options(
                    selectinload(Product.variants),
                    selectinload(Product.variations),
                )
            )
            products = result.scalars().all()

            desynced_products = []
            variants_to_mark_inherits = []

            for p in products:
                # If product has variations, it is a variable product; skip
                if p.variations and len(p.variations) > 0:
                    continue

                if not p.variants:
                    continue

                # Check if variants differ from product.base_price
                has_desync = False
                for v in p.variants:
                    if v.price != p.base_price:
                        has_desync = True
                        break

                if has_desync:
                    desynced_products.append(p)
                else:
                    # Check if any variant needs inherits_price = True
                    for v in p.variants:
                        if v.inherits_price is not True:
                            variants_to_mark_inherits.append(v)

            print(f"Found {len(desynced_products)} product(s) with desynchronized variant prices:")
            for p in desynced_products:
                print(f"  - Product '{p.title}' (ID: {p.id})")
                print(f"    Product base_price: {p.base_price} {p.currency}")
                for v in p.variants:
                    print(f"      Variant (ID: {v.id}, size: {v.size}, color: {v.color}): price={v.price} -> will be {p.base_price}")

            print(f"\nFound {len(variants_to_mark_inherits)} matching variant(s) needing inherits_price=True marker.")

            if not apply:
                print("\n[DRY RUN] No changes were written. Run with --apply to commit these repairs.")
                return

            # Apply fixes
            total_fixed = 0
            for p in desynced_products:
                for v in p.variants:
                    v.price = p.base_price
                    v.inherits_price = True
                    total_fixed += 1

            for v in variants_to_mark_inherits:
                v.inherits_price = True

            await db.commit()
            print(f"\n✅ Successfully updated {total_fixed} variant prices across {len(desynced_products)} product(s)!")
            print(f"✅ Successfully marked {len(variants_to_mark_inherits)} variant(s) with inherits_price=True!")

        except Exception as e:
            print(f"❌ Error during repair: {e}")
            await db.rollback()
            raise


def main():
    parser = argparse.ArgumentParser(description="Repair desynchronized product variant prices.")
    parser.add_argument("--apply", action="store_true", help="Apply changes to the database.")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without committing.")
    args = parser.parse_args()

    apply = args.apply and not args.dry_run
    asyncio.run(repair_prices(apply=apply))


if __name__ == "__main__":
    main()
