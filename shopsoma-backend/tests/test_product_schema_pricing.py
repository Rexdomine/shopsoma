from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from app.schemas.product import ProductResponse, ProductVariantResponse, VariationResponse


def _product_with_variation(*, price: Decimal | None, sale_price: Decimal | None):
    now = datetime.now(timezone.utc)
    variation = VariationResponse.model_construct(
        id=uuid4(),
        product_id=uuid4(),
        title="Red",
        type="color",
        color_hex=None,
        price=price,
        sale_price=sale_price,
        images=[],
        is_active=True,
        created_at=now,
        updated_at=now,
        size_stocks=[],
    )
    return ProductResponse.model_construct(
        id=uuid4(),
        base_price=Decimal("100.00"),
        variants=[],
        variations=[variation],
    )


def test_variation_sale_is_normalized_to_effective_variant_price():
    product = _product_with_variation(
        price=Decimal("100.00"),
        sale_price=Decimal("80.00"),
    )

    product.generate_variants_from_variations()  # pyright: ignore[reportCallIssue]

    variant = product.variants[0]
    assert variant.price == Decimal("80.00")
    assert variant.compare_at_price == Decimal("100.00")


def test_variation_sale_uses_product_fallback_as_regular_price():
    product = _product_with_variation(
        price=None,
        sale_price=Decimal("80.00"),
    )

    product.generate_variants_from_variations()  # pyright: ignore[reportCallIssue]

    variant = product.variants[0]
    assert variant.price == Decimal("80.00")
    assert variant.compare_at_price == Decimal("100.00")


def test_existing_variant_merges_matching_variation_compare_at_price():
    now = datetime.now(timezone.utc)
    variation = VariationResponse.model_construct(
        id=uuid4(),
        product_id=uuid4(),
        title="Red",
        type="color",
        color_hex=None,
        price=Decimal("100.00"),
        sale_price=Decimal("80.00"),
        images=[],
        is_active=True,
        created_at=now,
        updated_at=now,
        size_stocks=[],
    )
    variant = ProductVariantResponse.model_construct(
        id=uuid4(),
        product_id=variation.product_id,
        size=None,
        color="Red",
        color_hex=None,
        price=Decimal("200.00"),
        compare_at_price=None,
        stock=1,
        sku=None,
        is_available=True,
        created_at=now,
        updated_at=now,
    )
    product = ProductResponse.model_construct(
        id=variation.product_id,
        base_price=Decimal("200.00"),
        variants=[variant],
        variations=[variation],
    )

    product.generate_variants_from_variations()  # pyright: ignore[reportCallIssue]

    assert product.variants[0].price == Decimal("80.00")
    assert product.variants[0].compare_at_price == Decimal("100.00")


def test_existing_variant_matching_is_case_and_whitespace_insensitive():
    now = datetime.now(timezone.utc)
    variation = VariationResponse.model_construct(
        id=uuid4(), product_id=uuid4(), title="  red  ", type="color",
        color_hex=None, price=Decimal("100.00"), sale_price=Decimal("80.00"),
        images=[], is_active=True, created_at=now, updated_at=now, size_stocks=[],
    )
    variant = ProductVariantResponse.model_construct(
        id=uuid4(), product_id=variation.product_id, size=None, color="RED",
        color_hex=None, price=Decimal("200.00"), compare_at_price=None, stock=1,
        sku=None, is_available=True, created_at=now, updated_at=now,
    )
    product = ProductResponse.model_construct(
        id=variation.product_id, base_price=Decimal("200.00"), variants=[variant],
        variations=[variation],
    )

    product.generate_variants_from_variations()  # pyright: ignore[reportCallIssue]

    assert product.variants[0].price == Decimal("80.00")
    assert product.variants[0].compare_at_price == Decimal("100.00")


def test_colliding_normalized_variation_colors_do_not_choose_arbitrary_price():
    now = datetime.now(timezone.utc)
    variations = [
        VariationResponse.model_construct(
            id=uuid4(), product_id=uuid4(), title="Red", type="color", color_hex=None,
            price=Decimal("100.00"), sale_price=Decimal("80.00"), images=[],
            is_active=True, created_at=now, updated_at=now, size_stocks=[],
        ),
        VariationResponse.model_construct(
            id=uuid4(), product_id=uuid4(), title=" red ", type="color", color_hex=None,
            price=Decimal("120.00"), sale_price=None, images=[], is_active=True,
            created_at=now, updated_at=now, size_stocks=[],
        ),
    ]
    variant = ProductVariantResponse.model_construct(
        id=uuid4(), product_id=variations[0].product_id, size=None, color="RED",
        color_hex=None, price=Decimal("200.00"), compare_at_price=None, stock=1,
        sku=None, is_available=True, created_at=now, updated_at=now,
    )
    product = ProductResponse.model_construct(
        id=variations[0].product_id, base_price=Decimal("200.00"), variants=[variant],
        variations=variations,
    )

    product.generate_variants_from_variations()  # pyright: ignore[reportCallIssue]

    assert product.variants[0].price == Decimal("200.00")
    assert product.variants[0].compare_at_price is None


def test_inactive_variation_does_not_override_legacy_variant_price():
    now = datetime.now(timezone.utc)
    variation = VariationResponse.model_construct(
        id=uuid4(), product_id=uuid4(), title="Red", type="color", color_hex=None,
        price=Decimal("100.00"), sale_price=Decimal("80.00"), images=[],
        is_active=False, created_at=now, updated_at=now, size_stocks=[],
    )
    variant = ProductVariantResponse.model_construct(
        id=uuid4(), product_id=variation.product_id, size=None, color="red",
        color_hex=None, price=Decimal("200.00"), compare_at_price=None, stock=1,
        sku=None, is_available=True, created_at=now, updated_at=now,
    )
    product = ProductResponse.model_construct(
        id=variation.product_id, base_price=Decimal("200.00"), variants=[variant],
        variations=[variation],
    )

    product.generate_variants_from_variations()  # pyright: ignore[reportCallIssue]

    assert product.variants[0].price == Decimal("200.00")
    assert product.variants[0].compare_at_price is None


def test_existing_size_variant_merges_matching_size_variation_price():
    now = datetime.now(timezone.utc)
    variation = VariationResponse.model_construct(
        id=uuid4(),
        product_id=uuid4(),
        title="M",
        type="size",
        color_hex=None,
        price=Decimal("100.00"),
        sale_price=Decimal("80.00"),
        images=[],
        is_active=True,
        created_at=now,
        updated_at=now,
        size_stocks=[],
    )
    variant = ProductVariantResponse.model_construct(
        id=uuid4(),
        product_id=variation.product_id,
        size="M",
        color=None,
        color_hex=None,
        price=Decimal("80.00"),
        compare_at_price=None,
        stock=1,
        sku=None,
        is_available=True,
        created_at=now,
        updated_at=now,
    )
    product = ProductResponse.model_construct(
        id=variation.product_id,
        base_price=Decimal("200.00"),
        variants=[variant],
        variations=[variation],
    )

    product.generate_variants_from_variations()  # pyright: ignore[reportCallIssue]

    assert product.variants[0].price == Decimal("80.00")
    assert product.variants[0].compare_at_price == Decimal("100.00")


def test_null_or_invalid_variation_sale_does_not_override_regular_price():
    for sale_price in (None, Decimal("0.00"), Decimal("120.00")):
        product = _product_with_variation(
            price=Decimal("100.00"),
            sale_price=sale_price,
        )

        product.generate_variants_from_variations()  # pyright: ignore[reportCallIssue]

        variant = product.variants[0]
        assert variant.price == Decimal("100.00")
        assert variant.compare_at_price is None
