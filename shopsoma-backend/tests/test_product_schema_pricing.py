from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4
from types import SimpleNamespace
import pytest

from app.api.v1.products import _variation_inherits_parent_price
from app.schemas.product import (
    ProductResponse,
    ProductUpdate,
    ProductVariantResponse,
    ProductVariantCreate,
    SizeStockResponse,
    VariationResponse,
    VariationCreate,
    validate_variation_inventory_shape,
    variation_inventory_axis_signature,
)

def test_variation_inheritance_markers_preserve_equal_explicit_overrides():
    inherited = VariationCreate(
        title="Inherited",
        price=Decimal("100.00"),
        sale_price=Decimal("80.00"),
        inherits_price=True,
        inherits_sale_price=True,
    )
    explicit = VariationCreate(
        title="Explicit",
        price=Decimal("100.00"),
        sale_price=Decimal("80.00"),
        inherits_price=False,
        inherits_sale_price=False,
    )

    assert inherited.inherits_price is True
    assert inherited.inherits_sale_price is True
    assert explicit.inherits_price is False
    assert explicit.inherits_sale_price is False




def test_inheritance_marker_wins_over_equal_legacy_price_values():
    inherited = SimpleNamespace(
        price=Decimal("100.00"),
        inherits_price=True,
    )
    explicit = SimpleNamespace(
        price=Decimal("100.00"),
        inherits_price=False,
    )

    assert _variation_inherits_parent_price(
        inherited, "inherits_price", inherited.price, Decimal("100.00")
    ) is True
    assert _variation_inherits_parent_price(
        explicit, "inherits_price", explicit.price, Decimal("100.00")
    ) is False


def test_legacy_null_price_is_treated_as_inherited_without_a_marker():
    legacy = SimpleNamespace(price=None, inherits_price=None)

    assert _variation_inherits_parent_price(
        legacy, "inherits_price", legacy.price, Decimal("100.00")
    ) is True


def test_legacy_null_sale_is_custom_when_regular_price_is_custom():
    legacy = SimpleNamespace(sale_price=None, inherits_sale_price=None)

    assert _variation_inherits_parent_price(
        legacy,
        "inherits_sale_price",
        legacy.sale_price,
        Decimal("100.00"),
        null_value_inherits=False,
    ) is False


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
        inherits_price=None,
        inherits_sale_price=None,
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


def test_bare_size_variation_exposes_its_title_as_size():
    now = datetime.now(timezone.utc)
    variation = VariationResponse.model_construct(
        id=uuid4(), product_id=uuid4(), title="M", type="size", color_hex=None,
        price=None, sale_price=None, images=[], is_active=True,
        created_at=now, updated_at=now, size_stocks=[],
    )
    product = ProductResponse.model_construct(
        id=variation.product_id, base_price=Decimal("100.00"), variants=[],
        variations=[variation],
    )

    product.generate_variants_from_variations()  # pyright: ignore[reportCallIssue]

    assert product.variants[0].size == "M"
    assert product.variants[0].color is None


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


def test_existing_size_variant_inherits_sole_color_hex():
    now = datetime.now(timezone.utc)
    product_id = uuid4()
    color = VariationResponse.model_construct(
        id=uuid4(), product_id=product_id, title="Black", type="color",
        color_hex="#000000", price=None, sale_price=None, images=[], is_active=True,
        created_at=now, updated_at=now, size_stocks=[],
    )
    size = VariationResponse.model_construct(
        id=uuid4(), product_id=product_id, title="M", type="size",
        color_hex=None, price=None, sale_price=None, images=[], is_active=True,
        created_at=now, updated_at=now,
        size_stocks=[SizeStockResponse.model_construct(
            id=uuid4(), variation_id=uuid4(), size="M", stock=1,
            created_at=now, updated_at=now,
        )],
    )
    legacy_size = ProductVariantResponse.model_construct(
        id=uuid4(), product_id=product_id, size="M", color=None, color_hex=None,
        price=Decimal("100.00"), compare_at_price=None, stock=1, sku=None,
        is_available=True, created_at=now, updated_at=now,
    )
    product = ProductResponse.model_construct(
        id=product_id, base_price=Decimal("100.00"), variants=[legacy_size],
        variations=[color, size],
    )

    product.generate_variants_from_variations()  # pyright: ignore[reportCallIssue]

    assert product.variants[-1].color == "Black"
    assert product.variants[-1].color_hex == "#000000"


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


def test_mixed_legacy_and_size_stock_variants_expose_each_inventory_source_once():
    now = datetime.now(timezone.utc)
    product_id = uuid4()
    variation = VariationResponse.model_construct(
        id=uuid4(), product_id=product_id, title="M", type="size", color_hex=None,
        price=Decimal("100.00"), sale_price=Decimal("80.00"), images=[], is_active=True,
        created_at=now, updated_at=now,
        size_stocks=[SizeStockResponse.model_construct(
            id=uuid4(), variation_id=uuid4(), size="M", stock=3,
            created_at=now, updated_at=now,
        )],
    )
    color_variant = ProductVariantResponse.model_construct(
        id=uuid4(), product_id=product_id, size=None, color="Black", color_hex="#000000",
        price=Decimal("80.00"), compare_at_price=None, stock=2, sku=None,
        is_available=True, created_at=now, updated_at=now,
    )
    color_variation = VariationResponse.model_construct(
        id=uuid4(), product_id=product_id, title="Black", type="solid", color_hex="#000000",
        price=Decimal("100.00"), sale_price=Decimal("80.00"), images=[], is_active=True,
        created_at=now, updated_at=now, size_stocks=[],
    )
    product = ProductResponse.model_construct(
        id=product_id, base_price=Decimal("200.00"), variants=[color_variant],
        variations=[color_variation, variation],
    )

    product.generate_variants_from_variations()  # pyright: ignore[reportCallIssue]

    assert [(variant.size, variant.color, variant.stock) for variant in product.variants] == [
        (None, "Black", 2),
        ("M", "Black", 3),
    ]


def test_color_size_stocks_are_merged_with_legacy_color_variants():
    now = datetime.now(timezone.utc)
    product_id = uuid4()
    color_variation = VariationResponse.model_construct(
        id=uuid4(), product_id=product_id, title="Blue", type="color", color_hex="#0000FF",
        price=Decimal("100.00"), sale_price=Decimal("80.00"), images=[], is_active=True,
        created_at=now, updated_at=now,
        size_stocks=[SizeStockResponse.model_construct(
            id=uuid4(), variation_id=uuid4(), size="10", stock=4,
            created_at=now, updated_at=now,
        )],
    )
    legacy_variant = ProductVariantResponse.model_construct(
        id=uuid4(), product_id=product_id, size=None, color="Blue", color_hex="#0000FF",
        price=Decimal("80.00"), compare_at_price=None, stock=2, sku=None,
        is_available=True, created_at=now, updated_at=now,
    )
    product = ProductResponse.model_construct(
        id=product_id, base_price=Decimal("200.00"), variants=[legacy_variant],
        variations=[color_variation],
    )

    product.generate_variants_from_variations()  # pyright: ignore[reportCallIssue]

    assert [(variant.size, variant.color, variant.stock) for variant in product.variants] == [
        (None, "Blue", 2),
        ("10", "Blue", 4),
    ]
    assert product.variants[1].price == Decimal("80.00")
    assert product.variants[1].compare_at_price == Decimal("100.00")


def test_generated_size_stock_variant_does_not_populate_color_selector():
    now = datetime.now(timezone.utc)
    variation = VariationResponse.model_construct(
        id=uuid4(), product_id=uuid4(), title="M", type="size", color_hex=None,
        price=Decimal("100.00"), sale_price=None, images=[], is_active=True,
        created_at=now, updated_at=now,
        size_stocks=[SizeStockResponse.model_construct(
            id=uuid4(), variation_id=uuid4(), size="M", stock=3,
            created_at=now, updated_at=now,
        )],
    )
    product = ProductResponse.model_construct(
        id=variation.product_id, base_price=Decimal("200.00"), variants=[],
        variations=[variation],
    )

    product.generate_variants_from_variations()  # pyright: ignore[reportCallIssue]

    assert product.variants[0].size == "M"
    assert product.variants[0].color is None


def test_inactive_size_variation_is_not_merged_into_legacy_variants():
    now = datetime.now(timezone.utc)
    product_id = uuid4()
    variation = VariationResponse.model_construct(
        id=uuid4(), product_id=product_id, title="M", type="size", color_hex=None,
        price=Decimal("100.00"), sale_price=None, images=[], is_active=False,
        created_at=now, updated_at=now,
        size_stocks=[SizeStockResponse.model_construct(
            id=uuid4(), variation_id=uuid4(), size="M", stock=5,
            created_at=now, updated_at=now,
        )],
    )
    legacy_variant = ProductVariantResponse.model_construct(
        id=uuid4(), product_id=product_id, size="4", color=None, color_hex=None,
        price=Decimal("100.00"), compare_at_price=None, stock=2, sku=None,
        is_available=True, created_at=now, updated_at=now,
    )
    product = ProductResponse.model_construct(
        id=product_id, base_price=Decimal("100.00"), variants=[legacy_variant],
        variations=[variation],
    )

    product.generate_variants_from_variations()  # pyright: ignore[reportCallIssue]

    assert [variant.size for variant in product.variants] == ["4"]


def test_existing_size_variant_keeps_persisted_price_without_variation_override():
    now = datetime.now(timezone.utc)
    variation = VariationResponse.model_construct(
        id=uuid4(), product_id=uuid4(), title="M", type="size", color_hex=None,
        price=None, sale_price=None, images=[], is_active=True,
        created_at=now, updated_at=now, size_stocks=[],
    )
    variant = ProductVariantResponse.model_construct(
        id=uuid4(), product_id=variation.product_id, size="M", color=None,
        color_hex=None, price=Decimal("175.00"), compare_at_price=None, stock=1,
        sku=None, is_available=True, created_at=now, updated_at=now,
    )
    product = ProductResponse.model_construct(
        id=variation.product_id, base_price=Decimal("200.00"), variants=[variant],
        variations=[variation],
    )

    product.generate_variants_from_variations()  # pyright: ignore[reportCallIssue]

    assert product.variants[0].price == Decimal("175.00")
    assert product.variants[0].compare_at_price is None


def test_non_size_variation_type_is_treated_as_color_axis():
    variations = [
        VariationCreate.model_construct(type="pattern", is_active=True, sizes=[]),
        VariationCreate.model_construct(type="size", is_active=True, sizes=[]),
    ]

    try:
        validate_variation_inventory_shape(variations, [])
    except ValueError as exc:
        assert "Color and size variations" in str(exc)
    else:
        raise AssertionError("non-size variation types must be treated as color axes")


def test_color_backed_size_stock_rejects_all_legacy_inventory_rows():
    color_variation = VariationCreate.model_construct(
        type="color", is_active=True,
        sizes=[SimpleNamespace(size="M")],
    )
    legacy_variant = ProductVariantCreate.model_construct(color=None, size=None)

    try:
        validate_variation_inventory_shape([color_variation], [legacy_variant])
    except ValueError as exc:
        assert "color variation size stock" in str(exc)
    else:
        raise AssertionError("legacy inventory must not coexist with color-backed size stock")


def test_color_backed_size_stock_rejects_distinct_legacy_size_rows():
    color_variation = VariationCreate.model_construct(
        type="color", is_active=True,
        sizes=[SimpleNamespace(size="M")],
    )
    legacy_variant = ProductVariantCreate.model_construct(color=None, size="L")

    with pytest.raises(ValueError, match="color variation size stock"):
        validate_variation_inventory_shape([color_variation], [legacy_variant])


def test_size_axis_stock_allows_distinct_legacy_size_rows():
    size_variation = VariationCreate.model_construct(
        type="size", is_active=True,
        sizes=[SimpleNamespace(size="M")],
    )
    legacy_variant = ProductVariantCreate.model_construct(color=None, size="L")

    validate_variation_inventory_shape([size_variation], [legacy_variant])


def test_size_variation_labels_must_be_unique_after_normalization():
    variations = [
        VariationCreate.model_construct(title=" M ", type="size", is_active=True, sizes=[]),
        VariationCreate.model_construct(title="m", type="size", is_active=True, sizes=[]),
    ]

    try:
        validate_variation_inventory_shape(variations, [])
    except ValueError as exc:
        assert "Size variation labels must be unique" in str(exc)
    else:
        raise AssertionError("duplicate normalized size labels must be rejected")


def test_unmatched_bare_size_and_legacy_inventory_is_rejected():
    variations = [
        VariationCreate.model_construct(title="M", type="size", is_active=True, sizes=[]),
    ]
    legacy_variant = ProductVariantCreate.model_construct(size="L", color=None)

    try:
        validate_variation_inventory_shape(variations, [legacy_variant])
    except ValueError as exc:
        assert "match legacy size inventory labels" in str(exc)
    else:
        raise AssertionError("unmatched mixed size inventory must be rejected")


def test_bare_size_variation_rejects_generic_legacy_inventory_row():
    variation = VariationCreate.model_construct(
        title="M", type="size", is_active=True, sizes=[]
    )
    legacy_variant = ProductVariantCreate.model_construct(size=None, color=None)

    with pytest.raises(ValueError, match="Generic legacy variants"):
        validate_variation_inventory_shape([variation], [legacy_variant])


def test_bare_size_label_cannot_duplicate_nested_size_stock_label():
    bare = VariationCreate.model_construct(
        title="M", type="size", is_active=True, sizes=[]
    )
    nested = VariationCreate.model_construct(
        title="Regular", type="size", is_active=True,
        sizes=[SimpleNamespace(size="m")],
    )

    with pytest.raises(ValueError, match="Nested size-stock labels"):
        validate_variation_inventory_shape([bare, nested])


def test_inactive_duplicate_size_variation_labels_are_rejected_too():
    variations = [
        VariationCreate.model_construct(title="M", type="size", is_active=False, sizes=[]),
        VariationCreate.model_construct(title=" m ", type="size", is_active=True, sizes=[]),
    ]

    try:
        validate_variation_inventory_shape(variations, [])
    except ValueError as exc:
        assert "Size variation labels must be unique" in str(exc)
    else:
        raise AssertionError("inactive duplicate size labels must not persist")


def test_variation_inventory_axis_signature_normalizes_persisted_and_submitted_shapes():
    submitted = [
        VariationCreate.model_construct(
            title=" Black ", type="COLOR", is_active=True,
            sizes=[SimpleNamespace(size=" M ")],
        )
    ]
    persisted = [
        SimpleNamespace(
            title="black", type="color", is_active=True,
            size_stocks=[SimpleNamespace(size="m")],
        )
    ]

    assert variation_inventory_axis_signature(submitted) == variation_inventory_axis_signature(
        persisted
    )


def test_product_update_accepts_unchanged_grandfathered_variation_axes():
    """Compatibility-aware endpoint validation must see unchanged legacy axes."""
    ProductUpdate.model_validate(
        {
            "variations": [
                {"title": "Black", "type": "color"},
                {"title": "M", "type": "size"},
            ]
        }
    )


def test_nested_size_stock_labels_must_be_unique_across_size_variations():
    first = VariationCreate.model_construct(
        title="Regular", type="size", is_active=True,
        sizes=[SimpleNamespace(size="M")],
    )
    second = VariationCreate.model_construct(
        title="Petite", type="size", is_active=True,
        sizes=[SimpleNamespace(size=" m ")],
    )

    with pytest.raises(ValueError, match="Nested size-stock labels"):
        validate_variation_inventory_shape([first, second])
