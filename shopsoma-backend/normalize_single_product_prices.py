#!/usr/bin/env python3
"""
Management command to normalize single product prices.

For single products that have size options with different prices (or variant
prices that differ from the product's base_price):
1. Uses the first size option's price as the product's new Base Price / Sales Price (`base_price`).
2. Before updating `base_price`, calculates the percentage difference between the
   existing Product Price / Compare at Price (`compare_at_price`) and the existing
   Sales Price / Base Price (`base_price`):
       pct_diff = (old_compare_at_price - old_base_price) / old_base_price
3. Applies that percentage difference to the new `base_price` to compute the new
   Product Price / Compare at Price (`compare_at_price`):
       new_compare_at_price = new_base_price + (new_base_price * pct_diff)
4. Normalizes all size variants of the single product to `new_base_price` with
   `inherits_price = True`.

Usage:
    python normalize_single_product_prices.py
    python normalize_single_product_prices.py --dry-run
    python normalize_single_product_prices.py --apply
"""
import argparse
import asyncio
import os
import sys
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Optional

# Ensure backend directory is on sys.path and .env is loaded from backend root
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)
os.chdir(BACKEND_DIR)

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import AsyncSessionLocal
from app.models.product import Product, ProductType


TWOPLACES = Decimal("0.01")


def quantize_money(value: Decimal) -> Decimal:
    return value.quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def calculate_normalized_prices(
    old_base_price: Any,
    old_compare_at_price: Any,
    first_size_price: Any,
) -> tuple[Decimal, Optional[Decimal], Optional[Decimal]]:
    """
    Compute (new_base_price, new_compare_at_price, pct_diff) from the existing
    product prices and the first size option's price.
    """
    old_base = quantize_money(Decimal(str(old_base_price)))
    new_base = quantize_money(Decimal(str(first_size_price)))

    if old_compare_at_price is not None:
        old_compare = quantize_money(Decimal(str(old_compare_at_price)))
        if old_compare > Decimal("0") and old_base > Decimal("0"):
            pct_diff = (old_compare - old_base) / old_base
            new_compare = quantize_money(new_base + (new_base * pct_diff))
            return new_base, new_compare, pct_diff
        return new_base, old_compare, None

    return new_base, None, None


async def normalize_single_product_prices_in_session(
    db: AsyncSession,
    *,
    apply: bool = True,
) -> dict[str, Any]:
    """
    Inspect all single products and normalize those with mismatched or varying
    size option prices.
    """
    result = await db.execute(
        select(Product).options(
            selectinload(Product.variants),
            selectinload(Product.variations),
        )
    )
    products = result.scalars().all()

    normalized_products: list[dict[str, Any]] = []
    inherits_marked_count = 0

    for product in products:
        # Only process single products (no variable product variations)
        if product.product_type == ProductType.VARIABLE or (
            product.variations and len(product.variations) > 0
        ):
            continue

        if not product.variants:
            continue

        size_variants = [
            v for v in product.variants if v.size is not None and v.price is not None
        ]
        target_variants = size_variants if size_variants else [
            v for v in product.variants if v.price is not None
        ]
        if not target_variants:
            continue

        old_base = quantize_money(Decimal(str(product.base_price)))
        old_compare = (
            quantize_money(Decimal(str(product.compare_at_price)))
            if product.compare_at_price is not None
            else None
        )

        distinct_variant_prices = {
            quantize_money(Decimal(str(v.price))) for v in target_variants
        }
        has_different_size_prices = len(distinct_variant_prices) > 1
        has_base_price_mismatch = any(
            quantize_money(Decimal(str(v.price))) != old_base for v in target_variants
        )

        if has_different_size_prices or has_base_price_mismatch:
            first_variant = target_variants[0]
            first_size_price = quantize_money(Decimal(str(first_variant.price)))

            new_base, new_compare, pct_diff = calculate_normalized_prices(
                old_base_price=old_base,
                old_compare_at_price=old_compare,
                first_size_price=first_size_price,
            )

            product_report = {
                "product_id": str(product.id),
                "title": product.title,
                "currency": product.currency,
                "first_size": first_variant.size,
                "first_size_price": first_size_price,
                "old_base_price": old_base,
                "new_base_price": new_base,
                "old_compare_at_price": old_compare,
                "new_compare_at_price": new_compare,
                "pct_diff": pct_diff,
                "variants": [
                    {
                        "variant_id": str(v.id),
                        "size": v.size,
                        "old_price": quantize_money(Decimal(str(v.price))),
                        "new_price": new_base,
                    }
                    for v in product.variants
                ],
            }
            normalized_products.append(product_report)

            if apply:
                product.base_price = new_base
                product.compare_at_price = new_compare
                for v in product.variants:
                    v.price = new_base
                    v.inherits_price = True
        else:
            for v in product.variants:
                if v.inherits_price is not True:
                    inherits_marked_count += 1
                    if apply:
                        v.inherits_price = True

    if apply:
        await db.commit()

    return {
        "applied": apply,
        "normalized_count": len(normalized_products),
        "normalized_products": normalized_products,
        "inherits_marked_count": inherits_marked_count,
    }


async def run_command(apply: bool = True) -> dict[str, Any]:
    mode_label = "APPLY" if apply else "DRY RUN"
    print(f"=== Normalize Single Product Prices ({mode_label}) ===\n")

    async with AsyncSessionLocal() as db:
        try:
            summary = await normalize_single_product_prices_in_session(db, apply=apply)
        except Exception as exc:
            await db.rollback()
            print(f"Error normalizing single product prices: {exc}")
            raise

    normalized_products = summary["normalized_products"]
    print(f"Found {len(normalized_products)} single product(s) to normalize:")
    for item in normalized_products:
        pct_str = (
            f"{(item['pct_diff'] * Decimal('100')).quantize(TWOPLACES)}%"
            if item["pct_diff"] is not None
            else "N/A"
        )
        print(f"  - {item['title']} (ID: {item['product_id']})")
        print(
            f"    First size option: {item['first_size']!r} @ {item['first_size_price']} {item['currency']}"
        )
        print(
            f"    Base / Sales Price: {item['old_base_price']} -> {item['new_base_price']} {item['currency']}"
        )
        print(
            f"    Compare at / Product Price: {item['old_compare_at_price']} -> {item['new_compare_at_price']} "
            f"(pct diff: {pct_str})"
        )
        for v in item["variants"]:
            print(
                f"      Variant size={v['size']!r} (ID: {v['variant_id']}): "
                f"price {v['old_price']} -> {v['new_price']}, inherits_price=True"
            )

    if summary["inherits_marked_count"] > 0:
        print(
            f"\nMarked {summary['inherits_marked_count']} already-matching single-product variant(s) with inherits_price=True."
        )

    if apply:
        print(
            f"\nSuccessfully normalized {len(normalized_products)} single product(s)."
        )
    else:
        print("\n[DRY RUN] No changes committed. Run without --dry-run (or with --apply) to commit changes.")

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Normalize single product prices using the first size option's price."
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview price normalization changes without committing to the database.",
    )
    group.add_argument(
        "--apply",
        action="store_true",
        help="Apply and commit price normalization changes to the database (default).",
    )
    args = parser.parse_args()
    apply = not args.dry_run
    asyncio.run(run_command(apply=apply))


if __name__ == "__main__":
    main()
