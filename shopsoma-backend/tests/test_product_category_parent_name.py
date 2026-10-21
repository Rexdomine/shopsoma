import uuid

from app.models.category import Category
from app.models.product import Product


def test_category_parent_name_without_parent_loaded():
    category = Category(name="Child", slug="child")
    product = Product(
        title="Sample",
        base_price=10,
        vendor_id=uuid.uuid4(),
        category=category,
        currency="NGN",
    )

    assert product.category_parent_name is None


def test_category_parent_name_with_parent_loaded():
    parent = Category(name="Parent", slug="parent")
    category = Category(name="Child", slug="child", parent=parent)
    product = Product(
        title="Sample",
        base_price=10,
        vendor_id=uuid.uuid4(),
        category=category,
        currency="NGN",
    )

    assert product.category_parent_name == "Parent"


def test_product_categories_lineage_and_shop_edits():
    primary = Category(id=uuid.uuid4(), name="Women", slug="women")
    sub = Category(id=uuid.uuid4(), name="Women's Activewear", slug="women-activewear", parent=primary)
    child = Category(id=uuid.uuid4(), name="Shorts", slug="women-activewear-shorts", parent=sub)
    edit = Category(id=uuid.uuid4(), name="Casual", slug="shop-edits-occasion-wear-casual")

    product = Product(
        title="Cloud Shorts",
        base_price=36000,
        vendor_id=uuid.uuid4(),
        category=child,
        shop_edit_categories=[edit],
        currency="NGN",
    )

    assert product.categories == ["Women", "Women's Activewear", "Shorts", "Casual"]

