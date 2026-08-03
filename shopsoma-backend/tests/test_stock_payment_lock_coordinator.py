"""Statement-level coordinator regressions for Lane 2A-4B."""

import json
from pathlib import Path
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.models.product import (
    Product,
    ProductVariant,
    SizeEnum,
    SizeStock,
    Variation,
)
from app.models.stock_payment_persistence import coordinate_catalog_write


async def _catalog_subject(db_session, vendor_user):
    product = Product(
        id=uuid.uuid4(),
        vendor_id=vendor_user["vendor"].id,
        title="Coordinator product",
        description="Coordinator regression subject",
        base_price=100,
        total_stock=4,
        sku=f"COORD-{uuid.uuid4().hex[:12]}",
    )
    variant = ProductVariant(
        id=uuid.uuid4(),
        product_id=product.id,
        size="M",
        color="Black",
        price=100,
        stock=4,
        sku=f"COORD-V-{uuid.uuid4().hex[:10]}",
    )
    db_session.add_all([product, variant])
    await db_session.commit()
    return product, variant


async def _variation_subject(db_session, vendor_user):
    product = Product(
        id=uuid.uuid4(),
        vendor_id=vendor_user["vendor"].id,
        title="Cascade coordinator product",
        description="Cascade coordinator regression subject",
        base_price=100,
        total_stock=4,
        sku=f"CASCADE-{uuid.uuid4().hex[:10]}",
    )
    variation = Variation(
        id=uuid.uuid4(),
        product_id=product.id,
        title="Black",
        type="color",
        price=100,
    )
    size_stock = SizeStock(
        id=uuid.uuid4(),
        variation_id=variation.id,
        size=SizeEnum.M,
        stock=4,
    )
    db_session.add_all([product, variation, size_stock])
    await db_session.commit()
    return product, variation, size_stock


async def _coordinate(db_session, *keys: tuple[str, uuid.UUID]) -> None:
    payload = json.dumps(
        [
            {"subject_kind": kind, "subject_id": str(subject_id)}
            for kind, subject_id in keys
        ]
    )
    await db_session.execute(
        text("SELECT coordinate_stock_payment_write(CAST(:keys AS jsonb))"),
        {"keys": payload},
    )


@pytest.mark.asyncio
async def test_catalog_write_without_coordinator_preflight_fails_closed(
    db_session, vendor_user
) -> None:
    """Direct SQL cannot mutate a coordinated catalog subject by bypassing preflight."""

    _product, variant = await _catalog_subject(db_session, vendor_user)

    with pytest.raises(
        DBAPIError, match="stock/payment coordinator preflight required"
    ):
        await db_session.execute(
            text("UPDATE product_variants SET stock=stock-1 WHERE id=:id"),
            {"id": variant.id},
        )
    await db_session.rollback()


@pytest.mark.asyncio
async def test_catalog_write_succeeds_after_complete_coordinator_preflight(
    db_session, vendor_user
) -> None:
    """A complete ordered preflight enrolls the transaction for its exact write set."""

    product, variant = await _catalog_subject(db_session, vendor_user)
    await _coordinate(
        db_session,
        ("product", product.id),
        ("product_variant", variant.id),
    )
    await db_session.execute(
        text("UPDATE product_variants SET stock=stock-1 WHERE id=:id"),
        {"id": variant.id},
    )
    await db_session.commit()

    assert (
        await db_session.scalar(
            text("SELECT stock FROM product_variants WHERE id=:id"), {"id": variant.id}
        )
        == 3
    )


@pytest.mark.asyncio
async def test_catalog_coordinator_helper_resolves_variant_product_ancestry(
    db_session, vendor_user
) -> None:
    """Core writers can enroll a variant and its owning product as one complete set."""

    _product, variant = await _catalog_subject(db_session, vendor_user)

    await coordinate_catalog_write(db_session, product_variant_ids=[variant.id])
    await db_session.execute(
        text("UPDATE product_variants SET stock=stock-1 WHERE id=:id"),
        {"id": variant.id},
    )
    await db_session.commit()

    assert (
        await db_session.scalar(
            text("SELECT stock FROM product_variants WHERE id=:id"), {"id": variant.id}
        )
        == 3
    )


@pytest.mark.asyncio
async def test_direct_variation_delete_with_size_stock_accepts_complete_preflight(
    db_session, vendor_user
) -> None:
    """A direct parent delete keeps its enrolled descendant cascade valid."""

    product, variation, size_stock = await _variation_subject(db_session, vendor_user)
    await _coordinate(
        db_session,
        ("product", product.id),
        ("variation", variation.id),
        ("size_stock", size_stock.id),
    )

    await db_session.execute(
        text("DELETE FROM variations WHERE id=:id"), {"id": variation.id}
    )
    await db_session.commit()

    assert (
        await db_session.scalar(
            text("SELECT count(*) FROM variations WHERE id=:id"), {"id": variation.id}
        )
        == 0
    )
    assert (
        await db_session.scalar(
            text("SELECT count(*) FROM size_stocks WHERE id=:id"), {"id": size_stock.id}
        )
        == 0
    )


@pytest.mark.asyncio
async def test_product_delete_cascade_accepts_complete_descendant_preflight(
    db_session, vendor_user
) -> None:
    """Product→Variation→SizeStock cascade honors one complete coordinated set."""

    product, variation, size_stock = await _variation_subject(db_session, vendor_user)
    await _coordinate(
        db_session,
        ("product", product.id),
        ("variation", variation.id),
        ("size_stock", size_stock.id),
    )

    await db_session.execute(
        text("DELETE FROM products WHERE id=:id"), {"id": product.id}
    )
    await db_session.commit()

    assert (
        await db_session.scalar(
            text("SELECT count(*) FROM products WHERE id=:id"), {"id": product.id}
        )
        == 0
    )
    assert (
        await db_session.scalar(
            text("SELECT count(*) FROM variations WHERE id=:id"), {"id": variation.id}
        )
        == 0
    )
    assert (
        await db_session.scalar(
            text("SELECT count(*) FROM size_stocks WHERE id=:id"), {"id": size_stock.id}
        )
        == 0
    )


@pytest.mark.asyncio
async def test_orm_variation_delete_with_size_stock_coordinates_complete_subject_set(
    db_session, vendor_user
) -> None:
    """The products.py-style ORM replacement path enrolls parent and child writes."""

    _product, variation, size_stock = await _variation_subject(db_session, vendor_user)
    await db_session.delete(variation)
    await db_session.commit()

    assert (
        await db_session.scalar(
            text("SELECT count(*) FROM variations WHERE id=:id"), {"id": variation.id}
        )
        == 0
    )
    assert (
        await db_session.scalar(
            text("SELECT count(*) FROM size_stocks WHERE id=:id"), {"id": size_stock.id}
        )
        == 0
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("omitted_kind", ["product", "size_stock"])
async def test_variation_delete_cascade_rejects_partial_preflight(
    db_session, vendor_user, omitted_kind
) -> None:
    """Ancestor cascades still fail closed when any required subject is omitted."""

    product, variation, size_stock = await _variation_subject(db_session, vendor_user)
    keys = [
        ("product", product.id),
        ("variation", variation.id),
        ("size_stock", size_stock.id),
    ]
    await _coordinate(db_session, *(key for key in keys if key[0] != omitted_kind))

    with pytest.raises(
        DBAPIError, match="stock/payment coordinator preflight required"
    ):
        await db_session.execute(
            text("DELETE FROM variations WHERE id=:id"), {"id": variation.id}
        )
    await db_session.rollback()


@pytest.mark.asyncio
async def test_direct_size_stock_delete_without_preflight_fails_closed(
    db_session, vendor_user
) -> None:
    """Direct descendant deletion cannot use cascade handling to bypass ancestry locks."""

    _product, _variation, size_stock = await _variation_subject(db_session, vendor_user)
    with pytest.raises(
        DBAPIError, match="stock/payment coordinator preflight required"
    ):
        await db_session.execute(
            text("DELETE FROM size_stocks WHERE id=:id"), {"id": size_stock.id}
        )
    await db_session.rollback()


@pytest.mark.asyncio
async def test_direct_size_stock_delete_accepts_complete_preflight(
    db_session, vendor_user
) -> None:
    """A direct SizeStock delete accepts its complete authoritative ancestry set."""

    product, variation, size_stock = await _variation_subject(db_session, vendor_user)
    await _coordinate(
        db_session,
        ("product", product.id),
        ("variation", variation.id),
        ("size_stock", size_stock.id),
    )
    await db_session.execute(
        text("DELETE FROM size_stocks WHERE id=:id"), {"id": size_stock.id}
    )
    await db_session.commit()

    assert (
        await db_session.scalar(
            text("SELECT count(*) FROM size_stocks WHERE id=:id"), {"id": size_stock.id}
        )
        == 0
    )


@pytest.mark.asyncio
async def test_coordinator_rejects_duplicate_and_unknown_keys(
    db_session, vendor_user
) -> None:
    """Malformed key sets fail before any mutation or partial lock enrollment."""

    product, _variant = await _catalog_subject(db_session, vendor_user)
    product_id = product.id
    duplicate = json.dumps(
        [
            {"subject_kind": "product", "subject_id": str(product_id)},
            {"subject_kind": "product", "subject_id": str(product_id)},
        ]
    )
    with pytest.raises(DBAPIError, match="coordinator key set contains duplicates"):
        await db_session.execute(
            text("SELECT coordinate_stock_payment_write(CAST(:keys AS jsonb))"),
            {"keys": duplicate},
        )
    await db_session.rollback()

    unknown = json.dumps([{"subject_kind": "warehouse", "subject_id": str(product_id)}])
    with pytest.raises(DBAPIError, match="coordinator subject kind is invalid"):
        await db_session.execute(
            text("SELECT coordinate_stock_payment_write(CAST(:keys AS jsonb))"),
            {"keys": unknown},
        )
    await db_session.rollback()


def test_core_catalog_writers_use_explicit_preflight_or_document_fail_closed() -> None:
    app_root = Path(__file__).parents[1] / "app" / "api" / "v1"
    orders_source = (app_root / "orders.py").read_text()
    admin_source = (app_root / "admin.py").read_text()
    seed_source = (app_root / "seed.py").read_text()

    assert (
        "from app.models.stock_payment_persistence import coordinate_catalog_write"
        in orders_source
    )
    assert orders_source.count("await coordinate_catalog_write(") >= 2
    assert (
        "from app.models.stock_payment_persistence import coordinate_catalog_write"
        in admin_source
    )
    assert admin_source.count("await coordinate_catalog_write(") >= 2
    assert "unbounded reset intentionally fails closed" in admin_source
    assert "coordinator intentionally fails closed" in seed_source
