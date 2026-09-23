import io
import csv
import pytest
from httpx import AsyncClient

from app.api.v1.products import _parse_positive_decimal, _parse_image_urls


def test_bulk_image_url_validation_is_syntax_only_and_bounded() -> None:
    valid = "https://cdn.example.com/image.jpg?signature=a%2Bb%3D"
    errors = []
    assert _parse_image_urls({"image_1_url": valid}, 2, errors) == [valid]
    assert errors == []

    invalid = [
        "http://cdn.example.com/image.jpg",
        "https://user:password@cdn.example.com/image.jpg",
        "https://localhost/image.jpg",
        "https://127.0.0.1/image.jpg",
        "https://127.1/image.jpg",
        "https://2130706433/image.jpg",
        "https://0x7f000001/image.jpg",
        "https://cdn.example.com/image\\\\name.jpg",
        "https://bad_host.example/image.jpg",
        "https://bad..example/image.jpg",
        "https://cdn.example.com/image.jpg\n",
        "https://cdn.example.com/" + "x" * 2041,
    ]
    for value in invalid:
        errors = []
        assert _parse_image_urls({"image_1_url": value}, 2, errors) == []
        assert errors and errors[0]["row"] == 2


def test_bulk_image_url_validation_deduplicates_and_limits() -> None:
    row = {f"image_{index}_url": f"https://cdn.example.com/{index}.jpg" for index in range(1, 6)}
    row["image_5_url"] = row["image_1_url"]
    errors = []
    assert _parse_image_urls(row, 2, errors) == [f"https://cdn.example.com/{index}.jpg" for index in range(1, 5)]
    assert errors == []


def test_bulk_measurement_parser_rejects_below_storage_precision_and_non_finite() -> None:
    for value in ("0.0004", "NaN", "inf", "-inf"):
        errors = []
        assert _parse_positive_decimal(value, "weight_kg", 2, errors) is None
        assert errors[0]["field"] == "weight_kg"

    errors = []
    assert _parse_positive_decimal("0.001", "weight_kg", 2, errors) == 0.001
    assert errors == []

    errors = []
    assert _parse_positive_decimal("9999999.999", "weight_kg", 2, errors) == 9999999.999
    assert errors == []

    errors = []
    assert _parse_positive_decimal("10000000", "weight_kg", 2, errors) is None
    assert errors[0]["field"] == "weight_kg"


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
    from app.models.product import Product, Variation

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
        "color_name": "Blue",
        "color_hex": "#0000FF",
        "size": "M",
        "stock": "1",
        "variant_sku": "DRESS-A-BLUE-M",
        "variation_price": "120",
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

    variation_result = await db_session.execute(
        Variation.__table__.select().where(Variation.product_id == row.id)
    )
    variations = variation_result.fetchall()
    by_title = {variation.title: variation for variation in variations}
    assert by_title["Red"].inherits_price is True
    assert by_title["Red"].inherits_sale_price is True
    assert by_title["Blue"].inherits_price is False
    assert by_title["Blue"].inherits_sale_price is False


@pytest.mark.asyncio
async def test_bulk_upload_variable_rejects_product_sku_reused_by_multiple_products(client: AsyncClient, vendor_user, db_session):
    from app.models.category import Category

    category = Category(name="SKU Test Dresses", slug="sku-test-dresses")
    db_session.add(category)
    await db_session.commit()

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=[
        "product_title", "description", "category_slug", "currency", "base_price",
        "compare_at_price", "product_sku", "collection_name", "made_to_order",
        "made_to_order_timeline", "care_instructions", "fabric_composition",
        "color_name", "color_hex", "size", "stock", "variant_sku",
        "variation_price", "variation_sale_price",
    ])
    writer.writeheader()
    common = {
        "description": "Test dress", "category_slug": "sku-test-dresses", "currency": "USD",
        "base_price": "100", "compare_at_price": "120", "product_sku": "DUPLICATE-SKU",
        "collection_name": "", "made_to_order": "false", "made_to_order_timeline": "",
        "care_instructions": "", "fabric_composition": "", "color_name": "Red",
        "color_hex": "#FF0000", "size": "M", "stock": "2", "variation_price": "",
        "variation_sale_price": "",
    }
    writer.writerow({**common, "product_title": "Dress One", "variant_sku": "DUP-1"})
    writer.writerow({**common, "product_title": "Dress Two", "variant_sku": "DUP-2"})

    response = await client.post(
        "/api/v1/products/bulk-upload/variable",
        files={"file": ("duplicate.csv", output.getvalue(), "text/csv")},
        headers=vendor_user["headers"],
    )
    assert response.status_code == 422
    errors = response.json()["detail"]["errors"]
    assert sum(error["field"] == "product_sku" for error in errors) == 2
    assert all("multiple products" in error["message"] for error in errors if error["field"] == "product_sku")
