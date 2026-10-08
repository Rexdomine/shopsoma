"""
Product CRUD API endpoints
"""
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timezone
import csv
import io
import logging
import math
import ipaddress
import re
from pathlib import PurePosixPath
from urllib.parse import urlparse
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, and_, update
from sqlalchemy.orm import aliased, selectinload

from app.core.database import get_db
from app.api.dependencies import get_completed_vendor, get_current_admin
from app.services.vendor_visibility import customer_visible_vendor_product_filter
from app.models.user import User
from app.models.category import Category
from app.models.collection import Collection
from app.models.product import Product, ProductVariant, ProductImage, ProductStatus, ProductType, ModerationStatus, Variation, SizeStock, SizeEnum
from app.models.vendor import Vendor
from app.services.shop_edits import SHOP_EDIT_SLUGS
from app.models.stock_payment_persistence import coordinate_catalog_write
from app.services.product_moderation import (
    mark_product_content_pending,
    transition_product_moderation,
)
from app.services.image_service import image_service
from app.services.product_creation import build_product_graph, PRODUCT_RELATIONSHIPS
from app.services.product_duplication import duplicate_vendor_product
from app.services.product_image_storage import (
    clear_featured_storefront_references,
    clear_variation_image_references,
    lock_storage_keys,
    lock_and_validate_storage_keys,
    lock_and_validate_variation_image_urls,
    validate_image_upload,
    record_storage_cleanup,
)
from app.schemas.product import (
    ProductCreate,
    ProductUpdate,
    ProductResponse,
    ProductListResponse,
    ProductVariantCreate,
    ProductVariantUpdate,
    ProductVariantResponse,
    ProductImageCreate,
    ProductImageUpdate,
    ProductImageResponse,
    ProductModerationUpdate,
    validate_variation_inventory_shape,
    variation_inventory_axis_signature,
    normalize_color_value,
    unique_variations_by_color,
    unique_variations_by_size,
    effective_variation_price,
    variation_regular_price,
    variation_sale_price,
    VariationResponse,
    VariationUpdate,
    VariationPayload,
)
from app.services.variation_persistence import (
    sync_product_variations,
    update_single_variation,
    delete_single_variation,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/products", tags=["products"])

MAX_PRODUCT_IMAGES = 10


def _validate_vendor_storage_keys(vendor: Vendor, storage_keys: Optional[List[str]]) -> None:
    """Accept only keys issued for this vendor's product-image namespace."""
    if not storage_keys:
        return

    prefix = f"vendors/{vendor.user_id}/products/"
    prefix_parts = len(PurePosixPath(prefix.rstrip("/")).parts)
    for key in storage_keys:
        path = PurePosixPath(key)
        if (
            not key.startswith(prefix)
            or path.is_absolute()
            or any(part in {"", ".", ".."} for part in key.split("/"))
            or len(path.parts) <= prefix_parts
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Image storage key does not belong to vendor",
            )

def _variation_inherits_parent_price(
    variation: Variation,
    marker_name: str,
    persisted_value: Any,
    legacy_parent_value: Any,
    null_value_inherits: bool = True,
) -> bool:
    marker = getattr(variation, marker_name, None)
    if marker is not None:
        return marker
    if persisted_value is None:
        return null_value_inherits
    # A nullable marker plus a stored price is an unknown legacy state. Price
    # equality alone cannot distinguish an inherited value from an explicit
    # override, so preserve it rather than overwriting it on a parent edit.
    return False


def _sync_inherited_variation_prices(
    variations: list[Any],
    legacy_variants: list[Any],
    *,
    old_base_price: Any,
    old_compare_at_price: Any,
    new_base_price: Any,
    new_compare_at_price: Any,
) -> None:
    """Propagate parent price edits without overwriting explicit variation prices."""
    legacy_regular_price = old_compare_at_price or old_base_price
    legacy_effective_price = (
        old_base_price
        if old_compare_at_price is not None and old_base_price < legacy_regular_price
        else legacy_regular_price
    )

    # Single-product variants without Variation rows: generic rows sync only
    # when explicitly marked inherits_price=True to preserve explicit generic overrides.
    # Attribute-bearing rows (size/color options of a single product) propagate parent
    # price edits unless they were explicitly custom-priced differently from the parent.
    if not variations:
        new_regular_price = new_compare_at_price or new_base_price
        new_effective_price = (
            new_base_price
            if new_compare_at_price is not None and new_base_price < new_regular_price
            else new_regular_price
        )
        distinct_variant_prices = {
            legacy_variant.price
            for legacy_variant in legacy_variants
            if getattr(legacy_variant, "price", None) is not None
        }
        all_variants_share_price = len(distinct_variant_prices) == 1

        for legacy_variant in legacy_variants:
            is_generic = legacy_variant.size is None and legacy_variant.color is None
            if is_generic:
                # Null is an unknown legacy state. The migration backfills existing
                # generic rows to False because equality cannot distinguish an
                # explicit price from inherited pricing; never overwrite unknown
                # legacy data during a later parent edit.
                if getattr(legacy_variant, "inherits_price", None) is not True:
                    continue
                legacy_variant.price = new_effective_price
            else:
                # Attribute-bearing rows (size/color variants of single products).
                inherits = getattr(legacy_variant, "inherits_price", None) is True
                matches_prior_parent = (
                    legacy_variant.price == legacy_effective_price
                    or legacy_variant.price == old_base_price
                    or (old_compare_at_price is not None and legacy_variant.price == old_compare_at_price)
                )
                is_explicit_override = (
                    not inherits
                    and not matches_prior_parent
                    and not (all_variants_share_price and len(legacy_variants) > 1)
                )
                if is_explicit_override:
                    continue

                legacy_variant.price = new_effective_price
                legacy_variant.inherits_price = True
        return

    for variation in variations:
        inherits_regular_price = _variation_inherits_parent_price(
            variation, "inherits_price", variation.price, legacy_regular_price
        )
        inherits_sale_price = _variation_inherits_parent_price(
            variation,
            "inherits_sale_price",
            variation.sale_price,
            old_base_price,
            null_value_inherits=inherits_regular_price,
        )
        if getattr(variation, "inherits_sale_price", None) is None:
            inherits_sale_price = inherits_regular_price and inherits_sale_price
        if getattr(variation, "inherits_price", None) is None:
            variation.inherits_price = inherits_regular_price
        if getattr(variation, "inherits_sale_price", None) is None:
            variation.inherits_sale_price = inherits_sale_price
        if inherits_regular_price:
            variation.price = new_compare_at_price
        if inherits_sale_price:
            effective_regular_price = (
                variation.price
                if variation.price is not None
                else (new_compare_at_price or new_base_price)
            )
            variation.sale_price = (
                new_base_price
                if new_compare_at_price is not None
                and new_base_price < effective_regular_price
                else None
            )

        if not (inherits_regular_price or inherits_sale_price):
            continue
        variation_type = str(getattr(variation, "type", "color")).casefold()
        variation_title = normalize_color_value(variation.title)
        variation_index = (
            unique_variations_by_size(variations)
            if variation_type == "size"
            else unique_variations_by_color(variations)
        )
        if variation_index.get(variation_title) is not variation:
            continue
        for legacy_variant in legacy_variants:
            legacy_value = (
                legacy_variant.size if variation_type == "size" else legacy_variant.color
            )
            if normalize_color_value(legacy_value) == variation_title:
                # Legacy variants store the effective purchase price. Preserve
                # an explicit variation sale when only the regular price is
                # inherited from the product.
                legacy_variant.price = effective_variation_price(
                    variation.price,
                    variation_sale_price(
                        variation,
                        new_base_price,
                        parent_has_sale=new_compare_at_price is not None,
                    ),
                    new_base_price,
                    regular_price=variation_regular_price(
                        variation, new_base_price, new_compare_at_price
                    ),
                )


BULK_SINGLE_HEADERS = [
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
]
BULK_IMAGE_HEADERS = [f"image_{index}_url" for index in range(1, 6)]

BULK_VARIABLE_HEADERS = [
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
]


def _parse_image_urls(
    row: Dict[str, Optional[str]], row_index: int, errors: List[Dict[str, Any]]
) -> List[str]:
    """Validate optional hosted image links without network I/O; preserve URL bytes/order."""
    urls: List[str] = []
    for field in BULK_IMAGE_HEADERS:
        value = row.get(field)
        if value in (None, ""):
            continue
        try:
            # Reject characters browsers may silently strip or reinterpret.
            if len(value) > 2048 or "\\" in value or any(
                ch.isspace() or ord(ch) < 32 or ord(ch) == 127 for ch in value
            ):
                raise ValueError
            parsed = urlparse(value)
            host = parsed.hostname
            if (
                parsed.scheme != "https" or not host
                or parsed.username is not None or parsed.password is not None
            ):
                raise ValueError
            host = host.rstrip(".").lower()
            labels = host.split(".")
            if len(host) > 253 or len(labels) < 2 or any(
                not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
                for label in labels
            ):
                raise ValueError
            # A numeric final label triggers browser IPv4 parsing (including hex/octal).
            if re.fullmatch(r"(?:[0-9]+|0x[0-9a-f]+)", labels[-1]):
                raise ValueError
            if labels[-1] in {"localhost", "local", "internal", "lan", "home"}:
                raise ValueError
            try:
                ipaddress.ip_address(host)
            except ValueError:
                pass  # A syntactically valid DNS name; no DNS/reachability claim.
            else:
                raise ValueError
            if parsed.port is not None and not (1 <= parsed.port <= 65535):
                raise ValueError
            parsed_path = parsed.path.lower()
            if parsed_path.endswith((".heic", ".heif")) and "res.cloudinary.com" not in (parsed.hostname or ""):
                errors.append({
                    "row": row_index,
                    "field": field,
                    "message": "HEIC format images are only supported when hosted on Cloudinary or when converted to JPEG/PNG/WebP",
                })
                continue
        except (ValueError, UnicodeError):
            errors.append({
                "row": row_index, "field": field,
                "message": "Must be a public HTTPS URL of at most 2048 characters",
            })
            continue
        if value not in urls:
            urls.append(value)
    return urls


def _optimize_bulk_image_url(url: str, quality: str = "high") -> str:
    """
    Apply Cloudinary transformations to bulk upload image URLs for fast web rendering.
    Non-Cloudinary URLs are preserved unchanged to protect existing CDN contracts.
    """
    if not url or "res.cloudinary.com" not in url:
        return url

    match = re.match(
        r"^(https?://res\.cloudinary\.com/[^/]+/image/upload/)(?:((?:[a-z]_[^/,]+,?)+)/)?(.*)$",
        url,
        re.IGNORECASE,
    )
    if not match:
        return url

    prefix, existing_transforms, rest = match.groups()
    target_width = 400 if quality == "thumbnail" else 1600
    auto_transform = f"c_limit,w_{target_width},f_auto,q_auto"

    if existing_transforms:
        if "f_auto" in existing_transforms and "w_" in existing_transforms:
            transforms_to_use = existing_transforms
        else:
            transforms_to_use = f"{existing_transforms},{auto_transform}"
    else:
        transforms_to_use = auto_transform

    return f"{prefix}{transforms_to_use}/{rest}"


def _parse_bool(value: Optional[str]) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"true", "1", "yes", "y"}


def _parse_int(value: Optional[str], field: str, row: int, errors: List[Dict[str, Any]]) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError:
        errors.append({"row": row, "field": field, "message": "Must be an integer"})
        return None


def _parse_decimal(value: Optional[str], field: str, row: int, errors: List[Dict[str, Any]]) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError:
        errors.append({"row": row, "field": field, "message": "Must be a number"})
        return None


_MAX_PRODUCT_MEASUREMENT = 9999999.999


def _parse_positive_decimal(value: Optional[str], field: str, row: int, errors: List[Dict[str, Any]]) -> Optional[float]:
    parsed = _parse_decimal(value, field, row, errors)
    if parsed is not None and (
        not math.isfinite(parsed)
        or parsed < 0.001
        or parsed > _MAX_PRODUCT_MEASUREMENT
    ):
        errors.append({
            "row": row,
            "field": field,
            "message": "Must be between 0.001 and 9999999.999",
        })
        return None
    return parsed


def _sync_single_product_variant_inventory(product: Product) -> None:
    """Keep legacy variant stock aligned with single-product total_stock."""
    if product.product_type != ProductType.SINGLE:
        return
    if product.variations:
        return
    if not product.variants:
        return

    synced_stock = 0 if product.made_to_order else int(product.total_stock or 0)
    is_available = True if product.made_to_order else synced_stock > 0

    for variant in product.variants:
        # A single product may still carry explicit size/color variants even
        # without Variation rows. Only the axis-less legacy inventory row is
        # represented by the product-level total_stock field.
        if variant.size is not None or variant.color is not None:
            continue
        if variant.inherits_stock is True:
            variant.stock = synced_stock
            variant.is_available = is_available


def _sync_direct_variant_price_to_inherited_variation(
    variations: list[Any],
    *,
    price: Any,
    size: Any,
    color: Any,
) -> None:
    """Make a direct legacy-variant price edit authoritative when inherited."""
    if price is None:
        return

    matching_variation = None
    if color is not None:
        matching_variation = unique_variations_by_color(variations).get(
            normalize_color_value(color)
        )
    if matching_variation is None and size is not None:
        matching_variation = unique_variations_by_size(variations).get(
            normalize_color_value(size)
        )
    if matching_variation is None or not (
        matching_variation.inherits_price is True
        or matching_variation.inherits_sale_price is True
    ):
        return

    matching_variation.price = price
    matching_variation.sale_price = None
    matching_variation.inherits_price = False
    matching_variation.inherits_sale_price = False


async def _get_category_by_slug(db: AsyncSession, slug: str) -> Optional[Category]:
    result = await db.execute(select(Category).where(Category.slug == slug, Category.is_active == True))
    return result.scalar_one_or_none()


async def _get_collection_by_name(
    db: AsyncSession, vendor_id: UUID, name: str
) -> Optional["Collection"]:
    result = await db.execute(
        select(Collection).where(
            Collection.vendor_id == vendor_id,
            Collection.name == name
        )
    )
    return result.scalar_one_or_none()

# ============================================================================
# Product CRUD Endpoints
# ============================================================================

@router.post("", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def create_product(
    product_data: ProductCreate,
    vendor: Vendor = Depends(get_completed_vendor),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new product (vendors only)

    - **title**: Product title (required, 3-255 chars)
    - **description**: Product description
    - **base_price**: Base price (required, > 0)
    - **category_id**: Category UUID
    - **variants**: Optional list of variants
    - **images**: Optional list of images (max 10)
    """
    # Get vendor record
    if not vendor:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vendor profile not found"
        )

    if not vendor.approved:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vendor account not approved yet"
        )

    image_storage_keys = []
    for image_data in product_data.images or []:
        _validate_vendor_storage_keys(vendor, image_data.storage_keys)
        image_storage_keys.extend(image_data.storage_keys or [])
    if len(image_storage_keys) != len(set(image_storage_keys)):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Image storage keys must be unique",
        )
    if image_storage_keys:
        try:
            await lock_and_validate_storage_keys(db, image_storage_keys)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    for image_data in product_data.images or []:
        try:
            await validate_image_upload(
                db, image_data.image_url, image_data.thumbnail_url, image_data.storage_keys
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    product = await build_product_graph(db, product_data, vendor.id)

    await db.commit()
    await db.refresh(product)

    # Fetch with relationships
    result = await db.execute(
        select(Product)
        .options(*PRODUCT_RELATIONSHIPS)
        .where(Product.id == product.id)
    )
    product = result.scalar_one()

    return product


@router.post("/{product_id}/duplicate", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def duplicate_product(
    product_id: UUID,
    vendor: Vendor = Depends(get_completed_vendor),
    db: AsyncSession = Depends(get_db),
):
    """Create a private draft with independent, server-owned image copies."""
    if not vendor or not vendor.approved:
        raise HTTPException(status_code=403, detail="Vendor account not approved yet")
    return await duplicate_vendor_product(db, vendor, product_id)


@router.post("/bulk-upload/single", status_code=status.HTTP_201_CREATED)
async def bulk_upload_single_products(
    file: UploadFile = File(..., description="CSV file for single products"),
    vendor: Vendor = Depends(get_completed_vendor),
    db: AsyncSession = Depends(get_db)
):
    """Bulk upload single products from CSV (vendors only)."""
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a CSV file.")

    if not vendor or not vendor.approved:
        raise HTTPException(status_code=403, detail="Vendor account not approved.")

    content = await file.read()
    reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
    headers = reader.fieldnames or []
    missing_headers = [h for h in BULK_SINGLE_HEADERS if h not in headers]
    if missing_headers:
        raise HTTPException(
            status_code=422,
            detail={"message": "Missing required headers", "missing_headers": missing_headers},
        )

    errors: List[Dict[str, Any]] = []
    products_to_create: List[Product] = []
    sku_rows: Dict[str, List[int]] = {}

    for row_index, row in enumerate(reader, start=2):
        row_errors: List[Dict[str, Any]] = []
        image_urls = _parse_image_urls(row, row_index, row_errors)
        for image_url in image_urls:
            try:
                await validate_image_upload(db, image_url, image_url, None)
            except ValueError as exc:
                row_errors.append({"row": row_index, "field": "images", "message": str(exc)})
        title = (row.get("title") or "").strip()
        category_slug = (row.get("category_slug") or "").strip()
        currency = (row.get("currency") or "NGN").strip().upper()
        base_price = _parse_decimal(row.get("base_price"), "base_price", row_index, row_errors)
        compare_price = _parse_decimal(row.get("compare_at_price"), "compare_at_price", row_index, row_errors)
        total_stock = _parse_int(row.get("total_stock"), "total_stock", row_index, row_errors)
        weight_kg = _parse_positive_decimal(row.get("weight_kg"), "weight_kg", row_index, row_errors)
        length_cm = _parse_positive_decimal(row.get("length_cm"), "length_cm", row_index, row_errors)
        width_cm = _parse_positive_decimal(row.get("width_cm"), "width_cm", row_index, row_errors)
        height_cm = _parse_positive_decimal(row.get("height_cm"), "height_cm", row_index, row_errors)
        status_value = (row.get("status") or "draft").strip().lower()

        if not title:
            row_errors.append({"row": row_index, "field": "title", "message": "Title is required"})
        if not category_slug:
            row_errors.append({"row": row_index, "field": "category_slug", "message": "Category slug is required"})
        if currency not in {"NGN", "USD"}:
            row_errors.append({"row": row_index, "field": "currency", "message": "Currency must be NGN or USD"})
        if base_price is None:
            row_errors.append({"row": row_index, "field": "base_price", "message": "Base price is required"})
        if status_value not in {"draft", "active", "inactive", "archived"}:
            row_errors.append({"row": row_index, "field": "status", "message": "Invalid status"})

        category = None
        if category_slug:
            category = await _get_category_by_slug(db, category_slug)
            if not category:
                row_errors.append({"row": row_index, "field": "category_slug", "message": "Category slug not found"})

        collection = None
        collection_name = (row.get("collection_name") or "").strip()
        if collection_name:
            collection = await _get_collection_by_name(db, vendor.id, collection_name)
            if not collection:
                row_errors.append({"row": row_index, "field": "collection_name", "message": "Collection not found"})

        sku = (row.get("sku") or "").strip()
        if sku:
            sku_rows.setdefault(sku, []).append(row_index)

        if row_errors:
            errors.extend(row_errors)
            continue

        product = Product(
            vendor_id=vendor.id,
            title=title,
            description=(row.get("description") or "").strip() or None,
            category_id=category.id if category else None,
            collection_id=collection.id if collection else None,
            sku=(row.get("sku") or "").strip() or None,
            base_price=base_price,
            compare_at_price=compare_price,
            currency=currency,
            total_stock=total_stock or 0,
            status=ProductStatus(status_value),
            is_featured=False,
            product_type=ProductType.SINGLE,
            made_to_order=_parse_bool(row.get("made_to_order")),
            made_to_order_timeline=(row.get("made_to_order_timeline") or "").strip() or None,
            care_instructions=(row.get("care_instructions") or "").strip() or None,
            fabric_composition=(row.get("fabric_composition") or "").strip() or None,
            weight_kg=weight_kg,
            length_cm=length_cm,
            width_cm=width_cm,
            height_cm=height_cm,
            moderation_status=ModerationStatus.PENDING,
        )
        for display_order, image_url in enumerate(image_urls):
            product.images.append(ProductImage(
                image_url=_optimize_bulk_image_url(image_url, "high"),
                thumbnail_url=_optimize_bulk_image_url(image_url, "thumbnail"),
                display_order=display_order,
                is_primary=display_order == 0,
            ))
        products_to_create.append(product)

    for sku, rows in sku_rows.items():
        if len(rows) > 1:
            for row_index in rows:
                errors.append({"row": row_index, "field": "sku", "message": f"SKU '{sku}' is duplicated in this file"})
        elif await db.scalar(select(Product.id).where(Product.sku == sku).limit(1)):
            errors.append({"row": rows[0], "field": "sku", "message": f"SKU '{sku}' already exists"})

    if errors:
        raise HTTPException(status_code=422, detail={"message": "Validation failed", "errors": errors})

    db.add_all(products_to_create)
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    return {"success": True, "created_count": len(products_to_create)}


@router.post("/bulk-upload/variable", status_code=status.HTTP_201_CREATED)
async def bulk_upload_variable_products(
    file: UploadFile = File(..., description="CSV file for variable products"),
    vendor: Vendor = Depends(get_completed_vendor),
    db: AsyncSession = Depends(get_db)
):
    """Bulk upload variable products (with variations) from CSV."""
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a CSV file.")

    if not vendor or not vendor.approved:
        raise HTTPException(status_code=403, detail="Vendor account not approved.")

    content = await file.read()
    reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
    headers = reader.fieldnames or []
    missing_headers = [h for h in BULK_VARIABLE_HEADERS if h not in headers]
    if missing_headers:
        raise HTTPException(
            status_code=422,
            detail={"message": "Missing required headers", "missing_headers": missing_headers},
        )

    errors: List[Dict[str, Any]] = []
    grouped: Dict[str, Dict[str, Any]] = {}
    sku_rows: Dict[str, List[int]] = {}
    sku_groups: Dict[str, set[str]] = {}
    grouped_skus: Dict[str, Dict[str, List[int]]] = {}
    allowed_sizes = {size.value for size in SizeEnum}
    canonical_size_map = {size.value.upper(): size.value for size in SizeEnum}
    canonical_size_map.update({
        "ONE/SIZE": "One/Size",
        "ONE SIZE": "One/Size",
        "ONESIZE": "One/Size",
        "ONE-SIZE": "One/Size",
        "OS": "One/Size",
    })

    for row_index, row in enumerate(reader, start=2):
        row_errors: List[Dict[str, Any]] = []
        row_image_urls = _parse_image_urls(row, row_index, row_errors)
        for image_url in row_image_urls:
            try:
                await validate_image_upload(db, image_url, image_url, None)
            except ValueError as exc:
                row_errors.append({"row": row_index, "field": "images", "message": str(exc)})
        title = (row.get("product_title") or "").strip()
        category_slug = (row.get("category_slug") or "").strip()
        currency = (row.get("currency") or "NGN").strip().upper()
        base_price = _parse_decimal(row.get("base_price"), "base_price", row_index, row_errors)
        compare_price = _parse_decimal(row.get("compare_at_price"), "compare_at_price", row_index, row_errors)
        weight_kg = _parse_positive_decimal(row.get("weight_kg"), "weight_kg", row_index, row_errors)
        length_cm = _parse_positive_decimal(row.get("length_cm"), "length_cm", row_index, row_errors)
        width_cm = _parse_positive_decimal(row.get("width_cm"), "width_cm", row_index, row_errors)
        height_cm = _parse_positive_decimal(row.get("height_cm"), "height_cm", row_index, row_errors)
        color_name = (row.get("color_name") or "").strip()
        color_hex = (row.get("color_hex") or "").strip() or None
        raw_size = (row.get("size") or "").strip()
        size = canonical_size_map.get(raw_size.upper(), raw_size)
        stock = _parse_int(row.get("stock"), "stock", row_index, row_errors)
        variation_price = _parse_decimal(row.get("variation_price"), "variation_price", row_index, row_errors)
        variation_sale_price = _parse_decimal(row.get("variation_sale_price"), "variation_sale_price", row_index, row_errors)

        if not title:
            row_errors.append({"row": row_index, "field": "product_title", "message": "Product title is required"})
        if not category_slug:
            row_errors.append({"row": row_index, "field": "category_slug", "message": "Category slug is required"})
        if currency not in {"NGN", "USD"}:
            row_errors.append({"row": row_index, "field": "currency", "message": "Currency must be NGN or USD"})
        if base_price is None:
            row_errors.append({"row": row_index, "field": "base_price", "message": "Base price is required"})
        if not color_name:
            row_errors.append({"row": row_index, "field": "color_name", "message": "Color name is required"})
        if not size:
            row_errors.append({"row": row_index, "field": "size", "message": "Size is required"})
        elif size not in allowed_sizes:
            row_errors.append({"row": row_index, "field": "size", "message": "Invalid size value"})
        if stock is None:
            row_errors.append({"row": row_index, "field": "stock", "message": "Stock is required"})

        category = None
        if category_slug:
            category = await _get_category_by_slug(db, category_slug)
            if not category:
                row_errors.append({"row": row_index, "field": "category_slug", "message": "Category slug not found"})

        collection = None
        collection_name = (row.get("collection_name") or "").strip()
        if collection_name:
            collection = await _get_collection_by_name(db, vendor.id, collection_name)
            if not collection:
                row_errors.append({"row": row_index, "field": "collection_name", "message": "Collection not found"})

        product_sku = (row.get("product_sku") or "").strip()
        group_key = f"{title.lower()}::{category_slug.lower()}::{currency}"
        if product_sku:
            sku_rows.setdefault(product_sku, []).append(row_index)
            sku_groups.setdefault(product_sku, set()).add(group_key)
            grouped_skus.setdefault(group_key, {}).setdefault(product_sku, []).append(row_index)

        if row_errors:
            errors.extend(row_errors)
            continue

        if group_key not in grouped:
            grouped[group_key] = {
                "title": title,
                "description": (row.get("description") or "").strip() or None,
                "category_id": category.id if category else None,
                "collection_id": collection.id if collection else None,
                "currency": currency,
                "base_price": base_price,
                "compare_at_price": compare_price,
                "sku": (row.get("product_sku") or "").strip() or None,
                "made_to_order": _parse_bool(row.get("made_to_order")),
                "made_to_order_timeline": (row.get("made_to_order_timeline") or "").strip() or None,
                "care_instructions": (row.get("care_instructions") or "").strip() or None,
                "fabric_composition": (row.get("fabric_composition") or "").strip() or None,
                "weight_kg": weight_kg,
                "length_cm": length_cm,
                "width_cm": width_cm,
                "height_cm": height_cm,
                "images": [],
                "variations": {},
            }

        group_images = grouped[group_key]["images"]
        valid_image_urls = set(row_image_urls)
        for field in BULK_IMAGE_HEADERS:
            image_url = (row.get(field) or "").strip()
            if not image_url or image_url not in valid_image_urls or image_url in group_images:
                continue
            if len(group_images) >= 5:
                errors.append({
                    "row": row_index,
                    "field": field,
                    "message": "At most 5 unique image URLs are allowed per product",
                })
                continue
            group_images.append(image_url)

        variations = grouped[group_key]["variations"]
        variation_key = f"{color_name.lower()}::{color_hex or ''}"
        if variation_key not in variations:
            variations[variation_key] = {
                "title": color_name,
                "type": "color",
                "color_hex": color_hex,
                "price": variation_price,
                "sale_price": variation_sale_price,
                "images": [],
                "sizes": [],
            }

        for img_url in row_image_urls:
            if (
                img_url not in variations[variation_key]["images"]
                and len(variations[variation_key]["images"]) < 5
            ):
                variations[variation_key]["images"].append(img_url)

        variations[variation_key]["sizes"].append(
            {"size": size, "stock": stock}
        )

    for sku, rows in sku_rows.items():
        if len(sku_groups.get(sku, set())) > 1:
            for row_index in rows:
                errors.append({"row": row_index, "field": "product_sku", "message": f"Product SKU '{sku}' is used by multiple products in this file"})
        elif await db.scalar(select(Product.id).where(Product.sku == sku).limit(1)):
            for row_index in rows:
                errors.append({"row": row_index, "field": "product_sku", "message": f"Product SKU '{sku}' already exists"})

    for group_key, skus in grouped_skus.items():
        if len(skus) > 1:
            for rows in skus.values():
                for row_index in rows:
                    errors.append({
                        "row": row_index,
                        "field": "product_sku",
                        "message": "Rows for one product must use the same product SKU",
                    })

    if errors:
        raise HTTPException(status_code=422, detail={"message": "Validation failed", "errors": errors})

    created = 0
    for group in grouped.values():
        product = Product(
            vendor_id=vendor.id,
            title=group["title"],
            description=group["description"],
            category_id=group["category_id"],
            collection_id=group["collection_id"],
            sku=group["sku"],
            base_price=group["base_price"],
            compare_at_price=group["compare_at_price"],
            currency=group["currency"],
            total_stock=0,
            status=ProductStatus.DRAFT,
            is_featured=False,
            product_type=ProductType.VARIABLE,
            made_to_order=group["made_to_order"],
            made_to_order_timeline=group["made_to_order_timeline"],
            care_instructions=group["care_instructions"],
            fabric_composition=group["fabric_composition"],
            weight_kg=group["weight_kg"],
            length_cm=group["length_cm"],
            width_cm=group["width_cm"],
            height_cm=group["height_cm"],
            moderation_status=ModerationStatus.PENDING,
        )
        db.add(product)
        await db.flush()

        for display_order, image_url in enumerate(group["images"]):
            db.add(ProductImage(
                product_id=product.id,
                image_url=_optimize_bulk_image_url(image_url, "high"),
                thumbnail_url=_optimize_bulk_image_url(image_url, "thumbnail"),
                display_order=display_order,
                is_primary=display_order == 0,
            ))

        for variation_data in group["variations"].values():
            var_images = [
                _optimize_bulk_image_url(u, "high")
                for u in variation_data.get("images", [])
            ]
            variation = Variation(
                product_id=product.id,
                title=variation_data["title"],
                type=variation_data["type"],
                color_hex=variation_data["color_hex"],
                price=variation_data["price"],
                sale_price=variation_data["sale_price"],
                inherits_price=variation_data["price"] is None,
                inherits_sale_price=(
                    variation_data["sale_price"] is None
                    and variation_data["price"] is None
                ),
                images=var_images,
                is_active=True,
            )
            db.add(variation)
            await db.flush()

            for size_data in variation_data["sizes"]:
                size_stock = SizeStock(
                    variation_id=variation.id,
                    size=SizeEnum(size_data["size"]),
                    stock=size_data["stock"],
                )
                db.add(size_stock)

        created += 1

    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    return {"success": True, "created_count": created}

@router.get("", response_model=ProductListResponse)
async def list_products(
    search: Optional[str] = Query(None, max_length=255),
    category_id: Optional[UUID] = None,
    vendor_id: Optional[UUID] = None,
    status: Optional[str] = Query(None, pattern="^(draft|active|inactive|archived)$"),
    min_price: Optional[float] = Query(None, ge=0),
    max_price: Optional[float] = Query(None, ge=0),
    is_featured: Optional[bool] = None,
    in_stock: Optional[bool] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    sort_by: str = Query(default="created_at", pattern="^(created_at|title|base_price|orders_count|views_count)$"),
    sort_order: str = Query(default="desc", pattern="^(asc|desc)$"),
    db: AsyncSession = Depends(get_db)
):
    """
    List products with filters and pagination

    - Public storefront endpoint
    - Returns only customer-visible products
    """
    # Build query
    query = select(Product).options(*PRODUCT_RELATIONSHIPS)

    # Apply filters
    filters = [
        Product.moderation_status == ModerationStatus.APPROVED,
        customer_visible_vendor_product_filter(),
    ]
    if status:
        filters.append(Product.status == ProductStatus(status))
    else:
        filters.append(Product.status == ProductStatus.ACTIVE)

    # Search
    if search:
        search_terms = [t.strip() for t in search.split() if t.strip()]
        if search_terms:
            term_filters = []
            for term in search_terms:
                term_filter = or_(
                    Product.title.ilike(f"%{term}%"),
                    Product.description.ilike(f"%{term}%"),
                    Product.vendor.has(Vendor.business_name.ilike(f"%{term}%")),
                )
                term_filters.append(term_filter)
            filters.append(and_(*term_filters))

    # Category filter
    if category_id:
        category_result = await db.execute(select(Category).where(Category.id == category_id))
        requested_category = category_result.scalar_one_or_none()
        requested_slug = requested_category.slug if requested_category else None
        if requested_slug == "shop-edits":
            # The public landing page requests the parent category, while the
            # admin associations are stored on its four leaf edit categories.
            # Include only curated associations; do not broaden normal
            # category filtering or fall back to Product.category_id here.
            descendants = select(Category.id).where(Category.id == category_id).cte(
                "shop_edit_descendants", recursive=True
            )
            descendant_category = aliased(Category)
            descendants = descendants.union_all(
                select(descendant_category.id).where(
                    descendant_category.parent_id == descendants.c.id
                )
            )
            filters.append(
                Product.shop_edit_categories.any(
                    Category.id.in_(select(descendants.c.id))
                )
            )
        elif requested_slug in SHOP_EDIT_SLUGS.values():
            filters.append(Product.shop_edit_categories.any(Category.id == category_id))
        else:
            descendants = select(Category.id).where(Category.id == category_id).cte(
                "category_descendants", recursive=True
            )
            descendant_category = aliased(Category)
            descendants = descendants.union_all(
                select(descendant_category.id).where(
                    descendant_category.parent_id == descendants.c.id
                )
            )
            filters.append(Product.category_id.in_(select(descendants.c.id)))

    # Vendor filter
    if vendor_id:
        filters.append(Product.vendor_id == vendor_id)

    # Price range
    if min_price is not None:
        filters.append(Product.base_price >= min_price)
    if max_price is not None:
        filters.append(Product.base_price <= max_price)

    # Featured
    if is_featured is not None:
        filters.append(Product.is_featured == is_featured)

    # In stock
    if in_stock:
        filters.append(Product.total_stock > 0)

    # Apply all filters
    if filters:
        query = query.where(and_(*filters))

    # Count total
    count_query = select(func.count()).select_from(Product)
    if filters:
        count_query = count_query.where(and_(*filters))

    result = await db.execute(count_query)
    total = result.scalar()

    # Sorting
    sort_column = getattr(Product, sort_by)
    if sort_order == "desc":
        query = query.order_by(sort_column.desc())
    else:
        query = query.order_by(sort_column.asc())

    # Pagination
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)

    result = await db.execute(query)
    products = result.scalars().all()

    total_pages = (total + page_size - 1) // page_size

    return ProductListResponse(
        products=products,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )


@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(
    product_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """
    Get a single product by ID

    - Public storefront endpoint
    - Returns only customer-visible products
    """
    query = (
        select(Product)
        .options(*PRODUCT_RELATIONSHIPS)
        .where(
            Product.id == product_id,
            Product.status == ProductStatus.ACTIVE,
            Product.moderation_status == ModerationStatus.APPROVED,
            customer_visible_vendor_product_filter(),
        )
    )

    result = await db.execute(query)
    product = result.scalar_one_or_none()

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )

    if product.status != ProductStatus.ACTIVE or product.moderation_status != ModerationStatus.APPROVED:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )

    # Increment views
    product.views_count += 1
    await db.commit()

    # Reload with relationships to avoid lazy loading issues
    result = await db.execute(
        select(Product)
        .options(*PRODUCT_RELATIONSHIPS)
        .where(Product.id == product_id)
    )
    product = result.scalar_one()

    return product


@router.put("/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: UUID,
    product_data: ProductUpdate,
    vendor: Vendor = Depends(get_completed_vendor),
    db: AsyncSession = Depends(get_db)
):
    """
    Update a product (vendor only)

    - **product_id**: Product UUID
    - Only product owner can update
    """
    vendor_id = vendor.id

    if not vendor_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vendor profile not found"
        )

    # Get product
    result = await db.execute(
        select(Product)
        .options(*PRODUCT_RELATIONSHIPS)
        .where(Product.id == product_id)
    )
    product = result.scalar_one_or_none()

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )

    # Check ownership
    if product.vendor_id != vendor_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this product"
        )

    # Update fields
    update_data = product_data.model_dump(exclude_unset=True)

    old_base_price = product.base_price
    old_compare_at_price = product.compare_at_price
    inherited_price_update = "base_price" in update_data or "compare_at_price" in update_data

    # Handle variations separately for sync logic
    variations_data = update_data.pop("variations", None)
    variations_to_sync = product.variations

    content_rewrite = variations_data is not None or any(
        field in update_data for field in ["title", "description"]
    )
    if content_rewrite:
        await mark_product_content_pending(db=db, product_id=product_id)

    for field, value in update_data.items():
        if field == "status":
            setattr(product, field, ProductStatus(value))
        elif field == "size_guide":
            setattr(product, field, value.model_dump() if value is not None else None)
        else:
            setattr(product, field, value)

    # Sync variations if provided
    if variations_data is not None:
        variations_to_sync = await sync_product_variations(
            db,
            product,
            variations_data,
            inherited_price_update=inherited_price_update,
            is_admin=False,
        )

    if (product.product_type == ProductType.VARIABLE or getattr(product.product_type, "value", None) == "variable") and not product.made_to_order and product.variations:
        product.total_stock = sum(
            (s.stock or 0) for v in product.variations for s in getattr(v, "size_stocks", [])
        )
    elif any(field in update_data for field in ["total_stock", "made_to_order"]):
        _sync_single_product_variant_inventory(product)

    if inherited_price_update:
        _sync_inherited_variation_prices(
            variations_to_sync,
            product.variants or [],
            old_base_price=old_base_price,
            old_compare_at_price=old_compare_at_price,
            new_base_price=product.base_price,
            new_compare_at_price=product.compare_at_price,
        )

    await db.commit()

    # Reload with relationships to avoid lazy loading issues and stale
    # relationship collections after delete/recreate synchronization.
    result = await db.execute(
        select(Product)
        .options(*PRODUCT_RELATIONSHIPS)
        .where(Product.id == product_id)
        .execution_options(populate_existing=True)
    )
    product = result.scalar_one()

    return product


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(
    product_id: UUID,
    vendor: Vendor = Depends(get_completed_vendor),
    db: AsyncSession = Depends(get_db)
):
    """
    Delete a product (vendors only - own products)

    - Soft delete (sets status to archived)
    - Vendors can only delete their own products
    """
    # Get vendor
    result = await db.execute(
        select(Vendor.id).where(Vendor.id == vendor.id)
    )
    vendor_id = result.scalar_one_or_none()

    if not vendor_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vendor profile not found"
        )

    # Get product
    result = await db.execute(
        select(Product).where(Product.id == product_id)
    )
    product = result.scalar_one_or_none()

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )

    # Check ownership
    if product.vendor_id != vendor_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this product"
        )

    # Soft delete
    product.status = ProductStatus.ARCHIVED
    # Ensure archived products no longer count toward collection totals
    product.collection_id = None
    await db.commit()


# ============================================================================
# Product Variation Endpoints
# ============================================================================

@router.get("/{product_id}/variations", response_model=List[VariationResponse])
async def get_product_variations(
    product_id: UUID,
    vendor: Vendor = Depends(get_completed_vendor),
    db: AsyncSession = Depends(get_db)
):
    """Get all variations for a vendor's product"""
    result = await db.execute(
        select(Product)
        .options(*PRODUCT_RELATIONSHIPS)
        .where(Product.id == product_id)
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    if product.vendor_id != vendor.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to access this product")
    return product.variations


@router.put("/{product_id}/variations/{variation_id}", response_model=VariationResponse)
async def update_vendor_product_variation(
    product_id: UUID,
    variation_id: UUID,
    variation_data: VariationUpdate,
    vendor: Vendor = Depends(get_completed_vendor),
    db: AsyncSession = Depends(get_db)
):
    """
    Update a single selected variation for a vendor's product.
    Untouched variations and the product gallery remain unchanged.
    """
    result = await db.execute(
        select(Product)
        .options(*PRODUCT_RELATIONSHIPS)
        .where(Product.id == product_id)
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    if product.vendor_id != vendor.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to update this product")

    updated_variation = await update_single_variation(
        db=db,
        product=product,
        variation_id=variation_id,
        variation_data=variation_data,
        is_admin=False,
    )
    return updated_variation


@router.delete("/{product_id}/variations/{variation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_vendor_product_variation(
    product_id: UUID,
    variation_id: UUID,
    vendor: Vendor = Depends(get_completed_vendor),
    db: AsyncSession = Depends(get_db)
):
    """Delete a single variation from a vendor's product"""
    result = await db.execute(
        select(Product)
        .options(*PRODUCT_RELATIONSHIPS)
        .where(Product.id == product_id)
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    if product.vendor_id != vendor.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to update this product")

    await delete_single_variation(
        db=db,
        product=product,
        variation_id=variation_id,
        is_admin=False,
    )


# ============================================================================
# Product Variant Endpoints
# ============================================================================

@router.get("/{product_id}/variants")
async def get_product_variants(
    product_id: UUID,
    vendor: Vendor = Depends(get_completed_vendor),
    db: AsyncSession = Depends(get_db)
):
    """Get all variants for a vendor's product"""
    result = await db.execute(
        select(Product)
        .options(
            selectinload(Product.variants),
            selectinload(Product.variations).selectinload(Variation.size_stocks),
        )
        .where(Product.id == product_id)
    )
    product = result.scalar_one_or_none()

    if not product or product.vendor_id != vendor.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )

    variants_res = await db.execute(
        select(ProductVariant).where(ProductVariant.product_id == product_id)
    )
    product_variants = variants_res.scalars().all()

    variants_list = [
        {
            "id": str(v.id),
            "product_id": str(v.product_id),
            "sku": v.sku,
            "size": v.size,
            "color": v.color,
            "color_hex": v.color_hex,
            "price": float(v.price),
            "stock": v.stock,
            "is_available": v.is_available,
        }
        for v in product_variants
    ]

    existing_sizes = {v["size"] for v in variants_list if v["size"] is not None}
    if product.variations:
        for variation in product.variations:
            if not variation.is_active:
                continue
            for ss in variation.size_stocks:
                size_str = ss.size.value if hasattr(ss.size, "value") else str(ss.size)
                if size_str in existing_sizes:
                    continue
                var_price = float(variation.price if variation.price is not None else product.base_price)
                variants_list.append({
                    "id": str(ss.id),
                    "product_id": str(product.id),
                    "sku": None,
                    "size": size_str,
                    "color": variation.title if variation.type == "color" else None,
                    "color_hex": variation.color_hex,
                    "price": var_price,
                    "stock": ss.stock,
                    "is_available": bool(variation.is_active) and ss.stock > 0,
                })
                existing_sizes.add(size_str)

    return {
        "product_id": str(product_id),
        "variants": variants_list,
    }


@router.post("/{product_id}/variants", response_model=ProductVariantResponse, status_code=status.HTTP_201_CREATED)
async def create_variant(
    product_id: UUID,
    variant_data: ProductVariantCreate,
    vendor: Vendor = Depends(get_completed_vendor),
    db: AsyncSession = Depends(get_db)
):
    """Create a product variant"""
    # Check product ownership
    result = await db.execute(
        select(Vendor.id).where(Vendor.id == vendor.id)
    )
    vendor_id = result.scalar_one_or_none()

    result = await db.execute(
        select(Product)
        .options(
            selectinload(Product.variants),
            selectinload(Product.variations).selectinload(Variation.size_stocks),
        )
        .where(Product.id == product_id)
    )
    product = result.scalar_one_or_none()

    if not product or product.vendor_id != vendor_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )

    try:
        validate_variation_inventory_shape(product.variations, [*product.variants, variant_data])
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=[{"loc": ["body"], "msg": str(exc), "type": "value_error"}],
        ) from exc

    if variant_data.size:
        size_cand = variant_data.size.strip().casefold()
        v_sizes_res = await db.execute(
            select(ProductVariant.size).where(
                ProductVariant.product_id == product_id,
                ProductVariant.size.isnot(None),
            )
        )
        existing_sizes = {s.strip().casefold() for s in v_sizes_res.scalars().all()}
        for variation in product.variations:
            for ss in variation.size_stocks:
                s_val = ss.size.value if hasattr(ss.size, "value") else str(ss.size)
                existing_sizes.add(s_val.strip().casefold())
        if size_cand in existing_sizes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Size option '{variant_data.size}' already exists for this product",
            )

    explicit_inventory = bool(
        {"stock", "is_available"} & variant_data.model_fields_set
    )
    inherits_stock = (
        product.product_type == ProductType.SINGLE
        and not product.variations
        and variant_data.size is None
        and variant_data.color is None
        and not explicit_inventory
    )
    inherits_price = (
        not product.variations
        and variant_data.price == product.base_price
    )
    variant = ProductVariant(
        product_id=product_id,
        inherits_price=inherits_price,
        inherits_stock=inherits_stock,
        size=variant_data.size,
        color=variant_data.color,
        color_hex=variant_data.color_hex,
        price=variant_data.price,
        stock=(
            (0 if product.made_to_order else int(product.total_stock or 0))
            if inherits_stock
            else variant_data.stock
        ),
        sku=variant_data.sku,
        is_available=(
            (True if product.made_to_order else int(product.total_stock or 0) > 0)
            if inherits_stock
            else variant_data.is_available
        ),
    )
    db.add(variant)
    await mark_product_content_pending(db=db, product_id=product_id)
    await db.commit()
    await db.refresh(variant)

    return variant


@router.put("/{product_id}/variants/{variant_id}", response_model=ProductVariantResponse)
async def update_variant(
    product_id: UUID,
    variant_id: UUID,
    variant_data: ProductVariantUpdate,
    vendor: Vendor = Depends(get_completed_vendor),
    db: AsyncSession = Depends(get_db)
):
    """Update a product variant"""
    # Check ownership
    result = await db.execute(
        select(Vendor.id).where(Vendor.id == vendor.id)
    )
    vendor_id = result.scalar_one_or_none()

    result = await db.execute(
        select(Product)
        .options(
            selectinload(Product.variants),
            selectinload(Product.variations).selectinload(Variation.size_stocks),
        )
        .where(Product.id == product_id)
    )
    product = result.scalar_one_or_none()

    if not product or product.vendor_id != vendor_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )

    result = await db.execute(
        select(ProductVariant).where(
            and_(ProductVariant.id == variant_id, ProductVariant.product_id == product_id)
        )
    )
    variant = result.scalar_one_or_none()

    if not variant:
        # Check SizeStock fallback
        ss_result = await db.execute(
            select(SizeStock)
            .join(Variation, SizeStock.variation_id == Variation.id)
            .options(selectinload(SizeStock.variation))
            .where(
                SizeStock.id == variant_id,
                Variation.product_id == product_id,
            )
        )
        size_stock = ss_result.scalar_one_or_none()
        if not size_stock:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Variant not found"
            )

        update_dict = variant_data.model_dump(exclude_unset=True)
        if "stock" in update_dict:
            size_stock.stock = update_dict["stock"]
        if "price" in update_dict and size_stock.variation:
            size_stock.variation.price = update_dict["price"]
            size_stock.variation.inherits_price = False
        if "is_available" in update_dict and size_stock.variation:
            if not update_dict["is_available"] and size_stock.stock > 0:
                size_stock.stock = 0

        effective_size = size_stock.size.value if hasattr(size_stock.size, "value") else str(size_stock.size)
        if "size" in update_dict and update_dict["size"]:
            new_size_val = update_dict["size"]
            effective_size = new_size_val
            if new_size_val in SizeEnum._value2member_map_:
                size_stock.size = SizeEnum(new_size_val)
            else:
                current_price = update_dict.get("price") or (
                    size_stock.variation.price
                    if size_stock.variation and size_stock.variation.price is not None
                    else product.base_price
                )
                current_stock = update_dict.get("stock", size_stock.stock)
                is_avail = update_dict.get("is_available", current_stock > 0)
                new_v = ProductVariant(
                    id=variant_id,
                    product_id=product_id,
                    size=new_size_val,
                    color=size_stock.variation.title if size_stock.variation and size_stock.variation.type == "color" else None,
                    price=current_price,
                    stock=current_stock,
                    is_available=is_avail,
                )
                await db.delete(size_stock)
                db.add(new_v)
                await mark_product_content_pending(db=db, product_id=product_id)
                await db.commit()
                return ProductVariantResponse.model_validate(new_v)

        await mark_product_content_pending(db=db, product_id=product_id)
        await db.commit()
        await db.refresh(size_stock)
        return ProductVariantResponse(
            id=size_stock.id,
            product_id=product_id,
            size=effective_size,
            color=size_stock.variation.title if size_stock.variation and size_stock.variation.type == "color" else None,
            price=size_stock.variation.price if size_stock.variation and size_stock.variation.price is not None else product.base_price,
            stock=size_stock.stock,
            is_available=bool(size_stock.variation.is_active) and size_stock.stock > 0,
            created_at=size_stock.created_at,
            updated_at=size_stock.updated_at,
        )

    # Validate changes to inventory axes against the canonical variation inventory.
    # Price/stock/availability edits do not alter the inventory shape and can be
    # applied without re-running this cross-record validation.
    update_data = variant_data.model_dump(exclude_unset=True)
    inventory_axis_changed = any(
        field in update_data and update_data[field] != getattr(variant, field)
        for field in ("size", "color")
    )
    if inventory_axis_changed:
        candidate_variants = []
        for existing_variant in product.variants:
            candidate_data = {
                field: getattr(existing_variant, field)
                for field in (
                    "size",
                    "color",
                    "color_hex",
                    "price",
                    "stock",
                    "sku",
                    "is_available",
                )
            }
            if existing_variant.id == variant.id:
                candidate_data.update(update_data)
            candidate_variants.append(ProductVariantCreate.model_construct(**candidate_data))

        try:
            validate_variation_inventory_shape(product.variations, candidate_variants)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=[{"loc": ["body"], "msg": str(exc), "type": "value_error"}],
            ) from exc

    # An explicit stock or availability edit transfers inventory ownership from
    # the parent product back to this variant. Otherwise a later product-level
    # total_stock edit would overwrite the direct variant edit.
    if "stock" in update_data or "is_available" in update_data:
        variant.inherits_stock = False
    if "price" in update_data:
        variant.inherits_price = False
        _sync_direct_variant_price_to_inherited_variation(
            product.variations,
            price=update_data["price"],
            size=update_data.get("size", variant.size),
            color=update_data.get("color", variant.color),
        )

    for field, value in update_data.items():
        setattr(variant, field, value)

    if update_data:
        reviewable_variant_fields = {
            "size",
            "color",
            "color_hex",
            "price",
            "sku",
        }
        if reviewable_variant_fields.intersection(update_data):
            await mark_product_content_pending(db=db, product_id=product_id)
    await db.commit()
    await db.refresh(variant)

    return variant


@router.delete("/{product_id}/variants/{variant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_variant(
    product_id: UUID,
    variant_id: UUID,
    vendor: Vendor = Depends(get_completed_vendor),
    db: AsyncSession = Depends(get_db)
):
    """Delete a product variant"""
    # Check ownership
    result = await db.execute(
        select(Vendor.id).where(Vendor.id == vendor.id)
    )
    vendor_id = result.scalar_one_or_none()

    result = await db.execute(
        select(Product).where(Product.id == product_id)
    )
    product = result.scalar_one_or_none()

    if not product or product.vendor_id != vendor_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )

    # Get and delete variant
    result = await db.execute(
        select(ProductVariant).where(
            and_(ProductVariant.id == variant_id, ProductVariant.product_id == product_id)
        )
    )
    variant = result.scalar_one_or_none()

    if variant:
        await mark_product_content_pending(db=db, product_id=product_id)
        await db.delete(variant)
        await db.commit()
        return

    # Check SizeStock fallback
    ss_result = await db.execute(
        select(SizeStock)
        .join(Variation, SizeStock.variation_id == Variation.id)
        .options(selectinload(SizeStock.variation).selectinload(Variation.size_stocks))
        .where(
            SizeStock.id == variant_id,
            Variation.product_id == product_id,
        )
    )
    size_stock = ss_result.scalar_one_or_none()
    if not size_stock:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Variant not found"
        )

    variation = size_stock.variation
    await mark_product_content_pending(db=db, product_id=product_id)
    await db.delete(size_stock)
    if variation and variation.type.casefold() == "size" and len(variation.size_stocks) <= 1:
        await db.delete(variation)

    await db.commit()


# ============================================================================
# Product Image Endpoints
# ============================================================================

@router.post("/{product_id}/images", response_model=ProductImageResponse, status_code=status.HTTP_201_CREATED)
async def create_image(
    product_id: UUID,
    image_data: ProductImageCreate,
    vendor: Vendor = Depends(get_completed_vendor),
    db: AsyncSession = Depends(get_db)
):
    """Add a product image"""
    # Check ownership
    result = await db.execute(
        select(Vendor.id).where(Vendor.id == vendor.id)
    )
    vendor_id = result.scalar_one_or_none()

    # Reject requests for another vendor's product before claiming either
    # catalog lock. The locked recheck below remains authoritative if
    # ownership changes between this preflight and the write transaction.
    existing_vendor_id = await db.scalar(
        select(Product.vendor_id).where(Product.id == product_id)
    )
    if existing_vendor_id != vendor_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )

    # The moderation transition acquires the catalog coordinator before the
    # product row. Claim that coordinator first here as well; otherwise this
    # endpoint can hold the row while waiting on the coordinator and deadlock
    # with an admin moderation request using the opposite order.
    await coordinate_catalog_write(db, product_ids=[product_id], lock_only=True)

    # Lock the product row before counting so concurrent image additions
    # serialize against the same authoritative cap.
    result = await db.execute(
        select(Product).where(Product.id == product_id).with_for_update()
    )
    product = result.scalar_one_or_none()

    if not product or product.vendor_id != vendor_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )

    _validate_vendor_storage_keys(vendor, image_data.storage_keys)

    storage_keys = image_data.storage_keys or []
    if len(storage_keys) != len(set(storage_keys)):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Image storage keys must be unique",
        )
    if storage_keys:
        try:
            await lock_and_validate_storage_keys(db, storage_keys)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    try:
        await validate_image_upload(
            db, image_data.image_url, image_data.thumbnail_url, image_data.storage_keys
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    image_count = await db.scalar(
        select(func.count(ProductImage.id)).where(ProductImage.product_id == product_id)
    )
    if image_count >= MAX_PRODUCT_IMAGES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Products can have at most {MAX_PRODUCT_IMAGES} images",
        )

    if image_data.is_primary:
        await db.execute(
            update(ProductImage)
            .where(ProductImage.product_id == product_id)
            .values(is_primary=False)
        )

    # Create image
    image = ProductImage(
        product_id=product_id,
        **image_data.model_dump()
    )
    db.add(image)
    await mark_product_content_pending(db=db, product_id=product_id)
    await db.commit()
    await db.refresh(image)

    return image


@router.post("/{product_id}/images/{image_id}/primary", response_model=ProductImageResponse)
@router.patch("/{product_id}/images/{image_id}", response_model=ProductImageResponse)
@router.put("/{product_id}/images/{image_id}", response_model=ProductImageResponse)
async def update_image(
    product_id: UUID,
    image_id: UUID,
    image_data: Optional[ProductImageUpdate] = None,
    vendor: Vendor = Depends(get_completed_vendor),
    db: AsyncSession = Depends(get_db),
):
    """Update a product image (e.g. set as primary or change display order)"""
    result = await db.execute(
        select(Vendor.id).where(Vendor.id == vendor.id)
    )
    vendor_id = result.scalar_one_or_none()

    result = await db.execute(
        select(Product).where(Product.id == product_id)
    )
    product = result.scalar_one_or_none()

    if not product or product.vendor_id != vendor_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )

    images = list(
        (
            await db.scalars(
                select(ProductImage)
                .where(ProductImage.product_id == product_id)
                .order_by(ProductImage.display_order, ProductImage.created_at, ProductImage.id)
            )
        ).all()
    )
    image = next((item for item in images if item.id == image_id), None)
    if not image:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image not found"
        )

    changes = image_data.model_dump(exclude_unset=True) if image_data else {}
    if any(
        name in changes and changes[name] != getattr(image, name)
        for name in ("image_url", "thumbnail_url")
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Image URLs are immutable; use the upload endpoint",
        )

    new_order = changes.pop("display_order", None)
    make_primary = True if image_data is None else changes.pop("is_primary", None)
    order_target = image
    for key, value in changes.items():
        setattr(image, key, value)

    if make_primary is True:
        for item in images:
            item.is_primary = item.id == image_id
        if new_order is None:
            new_order = 0
    elif make_primary is False and image.is_primary:
        replacement = next((item for item in images if item.id != image_id), None)
        if replacement:
            image.is_primary = False
            replacement.is_primary = True
            order_target = replacement
            new_order = 0

    if new_order is not None:
        ordered = [item for item in images if item.id != order_target.id]
        if order_target.is_primary:
            new_order = 0
        elif any(item.is_primary for item in images):
            new_order = max(1, new_order)
        ordered.insert(min(new_order, len(ordered)), order_target)
        for index, item in enumerate(ordered):
            item.display_order = index
        images = ordered

    if images:
        primary = image if image.is_primary else next((item for item in images if item.is_primary), images[0])
        for item in images:
            item.is_primary = item is primary

    await mark_product_content_pending(db=db, product_id=product_id)
    await db.commit()
    await db.refresh(image)
    return image


@router.delete("/{product_id}/images/{image_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_image(
    product_id: UUID,
    image_id: UUID,
    vendor: Vendor = Depends(get_completed_vendor),
    db: AsyncSession = Depends(get_db)
):
    """Delete a product image"""
    # Check ownership
    result = await db.execute(
        select(Vendor.id).where(Vendor.id == vendor.id)
    )
    vendor_id = result.scalar_one_or_none()

    result = await db.execute(
        select(Product).where(Product.id == product_id)
    )
    product = result.scalar_one_or_none()

    if not product or product.vendor_id != vendor_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )

    # Get and delete image
    result = await db.execute(
        select(ProductImage).where(
            and_(ProductImage.id == image_id, ProductImage.product_id == product_id)
        )
    )
    image = result.scalar_one_or_none()

    if not image:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image not found"
        )

    was_primary = image.is_primary
    await mark_product_content_pending(db=db, product_id=product_id)
    storage_keys = list(image.storage_keys or [])
    if storage_keys:
        await lock_storage_keys(db, storage_keys)
    await db.delete(image)
    if was_primary:
        remaining_images = list(
            (
                await db.scalars(
                    select(ProductImage)
                    .where(and_(ProductImage.product_id == product_id, ProductImage.id != image_id))
                    .order_by(ProductImage.display_order, ProductImage.created_at, ProductImage.id)
                )
            ).all()
        )
        for idx, rem_img in enumerate(remaining_images):
            rem_img.is_primary = idx == 0
            rem_img.display_order = idx
    cleanup_record = None
    if storage_keys:
        await clear_featured_storefront_references(db, storage_keys)
        cleanup_record = await record_storage_cleanup(
            db, storage_keys, reason="vendor_image_delete",
            product_id=product_id, image_id=image_id, commit=False
        )
    await clear_variation_image_references(db, product_id, storage_keys, image.image_url)
    await db.commit()
    try:
        if storage_keys:
            cleanup = await image_service.delete_images(storage_keys)
            failed_keys = cleanup.get("failed_keys", []) if isinstance(cleanup, dict) else storage_keys
        else:
            failed_keys = []
    except Exception:
        logger.exception(
            "Vendor product image storage cleanup failed after durable row deletion",
            extra={"product_id": str(product_id), "image_id": str(image_id), "storage_keys": storage_keys},
        )
        failed_keys = storage_keys
    if not failed_keys and cleanup_record is not None:
        cleanup_record.resolved_at = datetime.now(timezone.utc)
        try:
            await db.commit()
        except Exception:
            await db.rollback()
            logger.exception(
                "Vendor product image cleanup resolution bookkeeping failed after storage deletion",
                extra={"product_id": str(product_id), "image_id": str(image_id), "storage_keys": storage_keys},
            )


# ============================================================================
# Admin Moderation Endpoints
# ============================================================================

@router.patch("/{product_id}/moderation", response_model=ProductResponse)
async def moderate_product(
    product_id: UUID,
    moderation_data: ProductModerationUpdate,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Moderate a product (admins only)

    - Approve, reject, or mark as pending
    - Add moderation notes
    """
    result = await db.execute(
        select(Product)
        .options(*PRODUCT_RELATIONSHIPS)
        .where(Product.id == product_id)
    )
    product = result.scalar_one_or_none()

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )

    await transition_product_moderation(
        db=db,
        product_id=product_id,
        admin_id=current_user.id,
        target_status=ModerationStatus(moderation_data.moderation_status),
        moderation_notes=moderation_data.moderation_notes,
        expected_updated_at=moderation_data.expected_updated_at,
    )

    # Reload with relationships to avoid lazy loading issues
    result = await db.execute(
        select(Product)
        .options(*PRODUCT_RELATIONSHIPS)
        .where(Product.id == product_id)
    )
    product = result.scalar_one()

    return product
