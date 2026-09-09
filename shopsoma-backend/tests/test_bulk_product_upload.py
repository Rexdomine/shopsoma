import io
import csv
import pytest
from httpx import AsyncClient

from app.api.v1.products import _parse_positive_decimal


def test_bulk_measurement_parser_rejects_below_storage_precision_and_non_finite() -> None:
    for value in ("0.0004", "NaN", "inf", "-inf"):
        errors = []
        assert _parse_positive_decimal(value, "weight_kg", 2, errors) is None
        assert errors[0]["field"] == "weight_kg"

    errors = []
    assert _parse_positive_decimal("0.001", "weight_kg", 2, errors) == 0.001
    assert errors == []


@pytest.mark.asyncio
async def test_bulk_upload_single_products_success(client: AsyncClient, vendor_user, db_session):
    from app.models.category import Category
    from app.models.product import Product

    category = Category(name="Menswear Shirts", slug="menswear-shirts")
    db_session.add(category)
    await db_session.commit()

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=[
        "title",
        "description",
        "category_slug",
        "currency",
        "base_price",
        "compare_at_price",
        "total_stock",
        "sku",
        "collection_name",
        "made_to_order",
        "made_to_order_timeline",
        "care_instructions",
        "fabric_composition",
        "status",
    ])
    writer.writeheader()
    writer.writerow({
        "title": "Test Shirt",
        "description": "Classic shirt",
        "category_slug": "menswear-shirts",
        "currency": "NGN",
        "base_price": "5000",
        "compare_at_price": "6000",
        "total_stock": "12",
        "sku": "TSHIRT-1",
        "collection_name": "",
        "made_to_order": "false",
        "made_to_order_timeline": "",
        "care_instructions": "",
        "fabric_composition": "",
        "status": "draft",
    })

    response = await client.post(
        "/api/v1/products/bulk-upload/single",
        files={"file": ("single.csv", output.getvalue(), "text/csv")},
        headers=vendor_user["headers"],
    )
    assert response.status_code == 201
    assert response.json()["created_count"] == 1

    result = await db_session.execute(
        Product.__table__.select().where(Product.title == "Test Shirt")
    )
    assert result.first() is not None


@pytest.mark.asyncio
async def test_bulk_upload_single_products_invalid_category(client: AsyncClient, vendor_user):
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=[
        "title",
        "description",
        "category_slug",
        "currency",
        "base_price",
        "compare_at_price",
        "total_stock",
        "sku",
        "collection_name",
        "made_to_order",
        "made_to_order_timeline",
        "care_instructions",
        "fabric_composition",
        "status",
    ])
    writer.writeheader()
    writer.writerow({
        "title": "Invalid Category Shirt",
        "description": "",
        "category_slug": "unknown-category",
        "currency": "NGN",
        "base_price": "5000",
        "compare_at_price": "",
        "total_stock": "5",
        "sku": "",
        "collection_name": "",
        "made_to_order": "false",
        "made_to_order_timeline": "",
        "care_instructions": "",
        "fabric_composition": "",
        "status": "draft",
    })

    response = await client.post(
        "/api/v1/products/bulk-upload/single",
        files={"file": ("single.csv", output.getvalue(), "text/csv")},
        headers=vendor_user["headers"],
    )
    assert response.status_code == 422
    errors = response.json()["detail"]["errors"]
    assert any(err["field"] == "category_slug" for err in errors)


@pytest.mark.asyncio
async def test_bulk_upload_variable_products_success(client: AsyncClient, vendor_user, db_session):
    from app.models.category import Category
    from app.models.product import Product

    category = Category(name="Womens Dresses", slug="womens-dresses")
    db_session.add(category)
    await db_session.commit()

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=[
        "product_title",
        "description",
        "category_slug",
        "currency",
        "base_price",
        "compare_at_price",
        "product_sku",
        "collection_name",
        "made_to_order",
        "made_to_order_timeline",
        "care_instructions",
        "fabric_composition",
        "color_name",
        "color_hex",
        "size",
        "stock",
        "variant_sku",
        "variation_price",
        "variation_sale_price",
    ])
    writer.writeheader()
    writer.writerow({
        "product_title": "Dress A",
        "description": "Elegant dress",
        "category_slug": "womens-dresses",
        "currency": "USD",
        "base_price": "120",
        "compare_at_price": "150",
        "product_sku": "DRESS-A",
        "collection_name": "",
        "made_to_order": "false",
        "made_to_order_timeline": "",
        "care_instructions": "",
        "fabric_composition": "",
        "color_name": "Red",
        "color_hex": "#FF0000",
        "size": "M",
        "stock": "3",
        "variant_sku": "DRESS-A-RED-M",
        "variation_price": "",
        "variation_sale_price": "",
    })
    writer.writerow({
        "product_title": "Dress A",
        "description": "Elegant dress",
        "category_slug": "womens-dresses",
        "currency": "USD",
        "base_price": "120",
        "compare_at_price": "150",
        "product_sku": "DRESS-A",
        "collection_name": "",
        "made_to_order": "false",
        "made_to_order_timeline": "",
        "care_instructions": "",
        "fabric_composition": "",
        "color_name": "Red",
        "color_hex": "#FF0000",
        "size": "L",
        "stock": "2",
        "variant_sku": "DRESS-A-RED-L",
        "variation_price": "",
        "variation_sale_price": "",
    })

    response = await client.post(
        "/api/v1/products/bulk-upload/variable",
        files={"file": ("variable.csv", output.getvalue(), "text/csv")},
        headers=vendor_user["headers"],
    )
    assert response.status_code == 201
    assert response.json()["created_count"] == 1

    result = await db_session.execute(
        Product.__table__.select().where(Product.title == "Dress A")
    )
    row = result.first()
    assert row is not None
