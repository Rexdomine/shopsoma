"""CSV image import persistence, atomic validation and public URL contracts."""
import csv
import io

import pytest
from sqlalchemy import func, select

from app.api.v1.products import BULK_IMAGE_HEADERS, BULK_SINGLE_HEADERS, BULK_VARIABLE_HEADERS, _parse_image_urls, _optimize_bulk_image_url
from app.models.category import Category
from app.models.product import Product, ProductImage, Variation


@pytest.fixture
async def image_category(db_session):
    category = Category(name="Image import shirts", slug="image-import-shirts")
    db_session.add(category)
    await db_session.commit()
    return category


def csv_data(mode, rows, include_images=True):
    headers = list(BULK_SINGLE_HEADERS if mode == "single" else BULK_VARIABLE_HEADERS)
    if include_images:
        headers += BULK_IMAGE_HEADERS
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=headers)
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def product_row(mode, **extra):
    row = {
        "description": "CSV image test", "category_slug": "image-import-shirts",
        "currency": "NGN", "base_price": "20000", "compare_at_price": "25000",
    }
    if mode == "single":
        row.update(title="CSV shirt", sku="CSV-IMAGE-SHIRT", total_stock="8", status="draft")
    else:
        row.update(product_title="CSV shirt", product_sku="CSV-IMAGE-SHIRT",
                   color_name="Blue", color_hex="#0000FF", size="S", stock="4",
                   variant_sku="CSV-IMAGE-SHIRT-BLUE-S")
    row.update(extra)
    return row


async def upload(client, vendor_user, mode, rows, include_images=True):
    return await client.post(
        f"/api/v1/products/bulk-upload/{mode}",
        files={"file": ("images.csv", csv_data(mode, rows, include_images), "text/csv")},
        headers=vendor_user["headers"],
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["single", "variable"])
async def test_csv_image_gallery_persists_and_round_trips(client, vendor_user, db_session, image_category, mode):
    urls = [f"https://cdn.example.com/photo-{i}.jpg?fit=crop,fill&key=a%2Bb%3D" for i in range(5)]
    row = product_row(mode, **dict(zip(BULK_IMAGE_HEADERS, urls)))
    rows = [row]
    if mode == "variable":
        rows += [product_row(mode, size="M", variant_sku="CSV-IMAGE-SHIRT-BLUE-M")]
    response = await upload(client, vendor_user, mode, rows)
    assert response.status_code == 201, response.text
    assert response.json()["created_count"] == 1
    product = await db_session.scalar(select(Product).where(Product.sku == "CSV-IMAGE-SHIRT"))
    images = (await db_session.scalars(select(ProductImage).where(
        ProductImage.product_id == product.id).order_by(ProductImage.display_order))).all()
    assert [image.image_url for image in images] == urls
    assert [image.thumbnail_url for image in images] == urls
    assert [image.display_order for image in images] == list(range(5))
    assert [image.is_primary for image in images] == [True, False, False, False, False]
    # Imported products remain moderation-gated on the public endpoint.
    public = await client.get(f"/api/v1/products/{product.id}")
    assert public.status_code == 404
    # Vendor detail is the actual edit/view surface for these draft products.
    detail = await client.get(f"/api/v1/vendor/products/{product.id}", headers=vendor_user["headers"])
    assert detail.status_code == 200, detail.text
    assert {image["image_url"] for image in detail.json()["images"]} == set(urls)
    assert sum(image["is_primary"] for image in detail.json()["images"]) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["single", "variable"])
async def test_csv_blank_leading_and_duplicate_images_are_ordered_once(client, vendor_user, db_session, image_category, mode):
    first, second = "https://cdn.example.com/first.jpg", "https://cdn.example.com/second.jpg"
    row = product_row(mode, image_2_url=first, image_3_url=first, image_5_url=second)
    rows = [row]
    if mode == "variable":
        rows += [{**row, "size": "M", "variant_sku": "CSV-IMAGE-SHIRT-BLUE-M"}]
    response = await upload(client, vendor_user, mode, rows)
    assert response.status_code == 201, response.text
    images = (await db_session.scalars(select(ProductImage).order_by(ProductImage.display_order))).all()
    assert [image.image_url for image in images] == [first, second]
    assert [image.is_primary for image in images] == [True, False]


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["single", "variable"])
@pytest.mark.parametrize("include_images", [False, True])
async def test_csv_no_images_remains_compatible(client, vendor_user, db_session, image_category, mode, include_images):
    response = await upload(client, vendor_user, mode, [product_row(mode)], include_images)
    assert response.status_code == 201, response.text
    assert await db_session.scalar(select(func.count()).select_from(Product)) == 1
    assert await db_session.scalar(select(func.count()).select_from(ProductImage)) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["single", "variable"])
async def test_csv_invalid_image_aborts_entire_batch(client, vendor_user, db_session, image_category, mode):
    valid = product_row(mode, image_1_url="https://cdn.example.com/valid.jpg")
    invalid = product_row(mode, image_3_url="http://localhost/private.jpg")
    if mode == "single":
        invalid.update(title="Invalid image shirt", sku="INVALID-IMAGE")
    else:
        invalid.update(product_title="Invalid image shirt", product_sku="INVALID-IMAGE")
    response = await upload(client, vendor_user, mode, [valid, invalid])
    assert response.status_code == 422, response.text
    assert any(error["row"] == 3 and error["field"] == "image_3_url" for error in response.json()["detail"]["errors"])
    assert await db_session.scalar(select(func.count()).select_from(Product)) == 0
    assert await db_session.scalar(select(func.count()).select_from(ProductImage)) == 0


@pytest.mark.asyncio
async def test_csv_variable_conflicting_skus_reject_before_writes(
    client, vendor_user, db_session, image_category
):
    first = product_row("variable", product_sku="CSV-IMAGE-SHIRT-A")
    second = product_row(
        "variable",
        product_sku="CSV-IMAGE-SHIRT-B",
        size="M",
        variant_sku="CSV-IMAGE-SHIRT-BLUE-M",
    )

    response = await upload(client, vendor_user, "variable", [first, second])

    assert response.status_code == 422, response.text
    errors = response.json()["detail"]["errors"]
    sku_errors = [error for error in errors if error["field"] == "product_sku"]
    assert [error["row"] for error in sku_errors] == [2, 3]
    assert all(
        error["message"] == "Rows for one product must use the same product SKU"
        for error in sku_errors
    )
    assert await db_session.scalar(select(func.count()).select_from(Product)) == 0
    assert await db_session.scalar(select(func.count()).select_from(ProductImage)) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["single", "variable"])
async def test_csv_image_commit_failure_rolls_back_products_and_images(
    client, vendor_user, db_session, image_category, monkeypatch, mode
):
    async def fail_commit():
        await db_session.flush()
        raise RuntimeError("injected commit failure")

    monkeypatch.setattr(db_session, "commit", fail_commit)
    with pytest.raises(RuntimeError, match="injected commit failure"):
        await upload(client, vendor_user, mode, [product_row(
            mode, image_1_url="https://cdn.example.com/rollback.jpg"
        )])
    assert await db_session.scalar(select(func.count()).select_from(Product)) == 0
    assert await db_session.scalar(select(func.count()).select_from(ProductImage)) == 0


@pytest.mark.asyncio
async def test_variable_image_limit_is_per_product_across_all_rows(client, vendor_user, db_session, image_category):
    row = product_row("variable", **{
        name: f"https://cdn.example.com/{index}.jpg" for index, name in enumerate(BULK_IMAGE_HEADERS)
    })
    second = product_row("variable", size="M", variant_sku="CSV-IMAGE-SHIRT-BLUE-M",
                         image_3_url="https://cdn.example.com/sixth.jpg")
    third = product_row("variable", size="L", variant_sku="CSV-IMAGE-SHIRT-BLUE-L")
    response = await upload(client, vendor_user, "variable", [row, second, third])
    assert response.status_code == 422, response.text
    limit_errors = [
        error for error in response.json()["detail"]["errors"]
        if "5 unique" in error["message"]
    ]
    assert limit_errors == [{
        "row": 3,
        "field": "image_3_url",
        "message": "At most 5 unique image URLs are allowed per product",
    }]
    assert await db_session.scalar(select(func.count()).select_from(Product)) == 0
    assert await db_session.scalar(select(func.count()).select_from(ProductImage)) == 0


@pytest.mark.parametrize("url", [
    "javascript:alert(1)", "data:image/png;base64,AAAA", "file:///tmp/a.jpg", "/images/a.jpg",
    "https://localhost/a.jpg", "https://localhost./a.jpg", "https://cdn.localhost/a.jpg",
    "https://cdn.local/a.jpg", "https://cdn.internal/a.jpg", "https://intranet/a.jpg",
    "https://127.0.0.1/a.jpg", "https://169.254.169.254/a.jpg", "https://[::1]/a.jpg",
    "https://127.1/a.jpg", "https://2130706433/a.jpg", "https://0x7f000001/a.jpg",
    "https://0177.0.0.1/a.jpg", "https://example.123/a.jpg",
    "https://user:secret@cdn.example.com/a.jpg", "https://@cdn.example.com/a.jpg",
    "https://bad_host.example/a.jpg", "https://bad..example/a.jpg", "https://-bad.example/a.jpg",
    "https://cdn.example.com:99999/a.jpg", "https://cdn.example.com:0/a.jpg",
    "https://cdn.example.com/a.jpg\n", " https://cdn.example.com/a.jpg", "https://cdn.example.com/a b.jpg",
    "https://cdn.example.com/\x00a.jpg", "https://cdn.example.com/\x7fa.jpg",
    "https://cdn.example.com\\@127.0.0.1/a.jpg",
    "https://cdn.example.com/" + "x" * 2048,
])
def test_csv_image_url_rejects_unsafe_or_malformed_targets(url):
    errors = []
    assert _parse_image_urls({"image_4_url": url}, 9, errors) == []
    assert len(errors) == 1
    assert errors[0]["row"] == 9
    assert errors[0]["field"] == "image_4_url"


@pytest.mark.parametrize("url", [
    "https://ace.cafe/image.jpg", "https://cdn.example.com/image.jpg?crop=10,20&key=a%2Bb%3D",
    "https://cdn.example.com:443/image.jpg", "https://xn--bcher-kva.example/image.jpg",
    "https://cdn.example.com/" + "x" * (2048 - len("https://cdn.example.com/")),
])
def test_csv_image_urls_preserve_valid_strings(url):
    errors = []
    assert _parse_image_urls({"image_1_url": url}, 2, errors) == [url]
    assert errors == []


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["single", "variable"])
async def test_csv_cannot_copy_managed_upload_as_keyless_image(
    client, vendor_user, db_session, image_category, mode
):
    url = f"https://cdn.example.com/vendors/{vendor_user['user'].id}/products/upload.jpg"
    response = await upload(client, vendor_user, mode, [product_row(mode, image_1_url=url)])
    assert response.status_code == 422, response.text
    assert "server-issued storage keys" in str(response.json()["detail"])
    assert await db_session.scalar(select(ProductImage.id)) is None


def test_optimize_bulk_image_url_unit():
    # Cloudinary raw URL
    url = "https://res.cloudinary.com/ekwntcvm/image/upload/v1790762856/ZIMORA_BLACK_WINDBREAKER.jpg"
    thumb = _optimize_bulk_image_url(url, "thumbnail")
    high = _optimize_bulk_image_url(url, "high")
    assert thumb == "https://res.cloudinary.com/ekwntcvm/image/upload/c_limit,w_400,f_auto,q_auto/v1790762856/ZIMORA_BLACK_WINDBREAKER.jpg"
    assert high == "https://res.cloudinary.com/ekwntcvm/image/upload/c_limit,w_1600,f_auto,q_auto/v1790762856/ZIMORA_BLACK_WINDBREAKER.jpg"

    # Cloudinary with existing transforms
    existing = "https://res.cloudinary.com/ekwntcvm/image/upload/c_scale,w_500/v1790762856/photo.jpg"
    assert _optimize_bulk_image_url(existing, "thumbnail") == "https://res.cloudinary.com/ekwntcvm/image/upload/c_scale,w_500,c_limit,w_400,f_auto,q_auto/v1790762856/photo.jpg"

    # Non-Cloudinary preserved
    cdn = "https://cdn.example.com/photo.jpg"
    assert _optimize_bulk_image_url(cdn, "thumbnail") == cdn
    assert _optimize_bulk_image_url(cdn, "high") == cdn


@pytest.mark.asyncio
async def test_csv_cloudinary_images_are_optimized_and_variation_images_populated(
    client, vendor_user, db_session, image_category
):
    black_url = "https://res.cloudinary.com/ekwntcvm/image/upload/v1/ZIMORA_BLACK.jpg"
    red_url = "https://res.cloudinary.com/ekwntcvm/image/upload/v1/ZIMORA_RED.heic"

    row1 = product_row("variable", color_name="Black", color_hex="#000000", size="S", variant_sku="WINDBREAKER-BLK-S", image_1_url=black_url)
    row2 = product_row("variable", color_name="Red", color_hex="#FF0000", size="M", variant_sku="WINDBREAKER-RED-M", image_1_url=red_url)

    response = await upload(client, vendor_user, "variable", [row1, row2])
    assert response.status_code == 201, response.text

    product = await db_session.scalar(select(Product).where(Product.sku == "CSV-IMAGE-SHIRT"))
    images = (await db_session.scalars(select(ProductImage).where(ProductImage.product_id == product.id).order_by(ProductImage.display_order))).all()
    assert len(images) == 2

    # Verify Cloudinary optimization applied to product images
    assert images[0].image_url == "https://res.cloudinary.com/ekwntcvm/image/upload/c_limit,w_1600,f_auto,q_auto/v1/ZIMORA_BLACK.jpg"
    assert images[0].thumbnail_url == "https://res.cloudinary.com/ekwntcvm/image/upload/c_limit,w_400,f_auto,q_auto/v1/ZIMORA_BLACK.jpg"

    assert images[1].image_url == "https://res.cloudinary.com/ekwntcvm/image/upload/c_limit,w_1600,f_auto,q_auto/v1/ZIMORA_RED.heic"
    assert images[1].thumbnail_url == "https://res.cloudinary.com/ekwntcvm/image/upload/c_limit,w_400,f_auto,q_auto/v1/ZIMORA_RED.heic"

    # Verify variation images populated
    variations = (await db_session.scalars(select(Variation).where(Variation.product_id == product.id).order_by(Variation.title))).all()
    assert len(variations) == 2
    black_var = next(v for v in variations if v.title == "Black")
    red_var = next(v for v in variations if v.title == "Red")

    assert black_var.images == ["https://res.cloudinary.com/ekwntcvm/image/upload/c_limit,w_1600,f_auto,q_auto/v1/ZIMORA_BLACK.jpg"]
    assert red_var.images == ["https://res.cloudinary.com/ekwntcvm/image/upload/c_limit,w_1600,f_auto,q_auto/v1/ZIMORA_RED.heic"]


@pytest.mark.asyncio
async def test_csv_non_cloudinary_heic_is_rejected(
    client, vendor_user, db_session, image_category
):
    bad_heic = "https://cdn.example.com/unsupported.heic"
    response = await upload(client, vendor_user, "single", [product_row("single", image_1_url=bad_heic)])
    assert response.status_code == 422, response.text
    errors = response.json()["detail"]["errors"]
    assert any("HEIC format images are only supported when hosted on Cloudinary" in e["message"] for e in errors)
