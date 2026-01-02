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
