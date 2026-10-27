"""Tests for single product price normalization management command."""
from decimal import Decimal
import uuid
import pytest

from app.models.product import Product, ProductStatus, ProductType, ProductVariant, Variation
from normalize_single_product_prices import (
    calculate_normalized_prices,
    normalize_single_product_prices_in_session,
)


def test_calculate_normalized_prices_with_compare_at_price():
    """
    Checks that percentage difference between compare_at_price and base_price is
    preserved and applied to the first size's price.
    """
    # Example: base_price = 20000, compare_at_price = 25000 (25% diff), first_size_price = 19000
    # Expected: new_base = 19000.00, new_compare = 19000 + (19000 * 0.25) = 23750.00
    new_base, new_compare, pct_diff = calculate_normalized_prices(
        old_base_price=Decimal("20000.00"),
        old_compare_at_price=Decimal("25000.00"),
        first_size_price=Decimal("19000.00"),
    )
    assert new_base == Decimal("19000.00")
    assert new_compare == Decimal("23750.00")
    assert pct_diff == Decimal("0.25")


def test_calculate_normalized_prices_20_percent_diff():
    """
    Example: base_price = 100, compare_at_price = 120 (20% diff), first_size_price = 60
    Expected: new_base = 60.00, new_compare = 60 + (60 * 0.20) = 72.00
    """
    new_base, new_compare, pct_diff = calculate_normalized_prices(
        old_base_price=Decimal("100.00"),
        old_compare_at_price=Decimal("120.00"),
        first_size_price=Decimal("60.00"),
    )
    assert new_base == Decimal("60.00")
    assert new_compare == Decimal("72.00")
    assert pct_diff == Decimal("0.2")


def test_calculate_normalized_prices_without_compare_at_price():
    """When compare_at_price is None, new_compare_at_price remains None."""
    new_base, new_compare, pct_diff = calculate_normalized_prices(
        old_base_price=Decimal("100.00"),
        old_compare_at_price=None,
        first_size_price=Decimal("97.00"),
    )
    assert new_base == Decimal("97.00")
    assert new_compare is None
    assert pct_diff is None


@pytest.mark.asyncio
async def test_normalize_single_product_prices_in_session(db_session, vendor_user):
    """
    Verifies that single products with different size option prices have:
    1. base_price updated to the first size option's price,
    2. compare_at_price updated using the prior percentage difference,
    3. all size variants updated to match the new base_price with inherits_price=True,
    while variable products are untouched.
    """
    vendor = vendor_user["vendor"]

    # Single product with different size prices and compare_at_price
    single_product = Product(
        id=uuid.uuid4(),
        vendor_id=vendor.id,
        title="Krok Shoe Test",
        description="Handcrafted shoes",
        base_price=Decimal("20000.00"),
        compare_at_price=Decimal("25000.00"),
        currency="NGN",
        total_stock=15,
        status=ProductStatus.ACTIVE,
        product_type=ProductType.SINGLE,
    )
    db_session.add(single_product)
    await db_session.flush()

    v1 = ProductVariant(
        id=uuid.uuid4(),
        product_id=single_product.id,
        size="8",
        price=Decimal("19000.00"),
        stock=5,
        is_available=True,
        inherits_price=False,
    )
    v2 = ProductVariant(
        id=uuid.uuid4(),
        product_id=single_product.id,
        size="10",
        price=Decimal("21000.00"),
        stock=5,
        is_available=True,
        inherits_price=False,
    )
    v3 = ProductVariant(
        id=uuid.uuid4(),
        product_id=single_product.id,
        size="12",
        price=Decimal("18000.00"),
        stock=5,
        is_available=True,
        inherits_price=False,
    )
    db_session.add_all([v1, v2, v3])

    # Variable product should NOT be modified
    variable_product = Product(
        id=uuid.uuid4(),
        vendor_id=vendor.id,
        title="Variable Dress",
        description="Variable product",
        base_price=Decimal("50000.00"),
        compare_at_price=Decimal("60000.00"),
        currency="NGN",
        total_stock=10,
        status=ProductStatus.ACTIVE,
        product_type=ProductType.VARIABLE,
    )
    db_session.add(variable_product)
    await db_session.flush()

    variation = Variation(
        id=uuid.uuid4(),
        product_id=variable_product.id,
        title="Gold",
        type="color",
        price=Decimal("65000.00"),
        sale_price=Decimal("55000.00"),
        is_active=True,
    )
    var_variant = ProductVariant(
        id=uuid.uuid4(),
        product_id=variable_product.id,
        size="M",
        color="Gold",
        price=Decimal("55000.00"),
        stock=10,
        is_available=True,
        inherits_price=False,
    )
    db_session.add_all([variation, var_variant])
    await db_session.commit()

    summary = await normalize_single_product_prices_in_session(db_session, apply=True)

    assert summary["normalized_count"] >= 1
    await db_session.refresh(single_product)
    await db_session.refresh(v1)
    await db_session.refresh(v2)
    await db_session.refresh(v3)
    await db_session.refresh(variable_product)
    await db_session.refresh(var_variant)

    # Single product updated to first size price (19000.00) and compare_at_price +25% (23750.00)
    assert single_product.base_price == Decimal("19000.00")
    assert single_product.compare_at_price == Decimal("23750.00")
    for variant in (v1, v2, v3):
        assert variant.price == Decimal("19000.00")
        assert variant.inherits_price is True

    # Variable product untouched
    assert variable_product.base_price == Decimal("50000.00")
    assert variable_product.compare_at_price == Decimal("60000.00")
    assert var_variant.price == Decimal("55000.00")
