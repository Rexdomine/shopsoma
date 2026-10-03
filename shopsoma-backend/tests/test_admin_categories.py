"""
Tests for Admin Category Management (Primary Category, Subcategory, Child Category)
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.category import Category


@pytest.mark.asyncio
async def test_admin_create_primary_subcategory_and_child_category(
    client: AsyncClient,
    admin_user: dict,
    db_session: AsyncSession
):
    headers = admin_user["headers"]

    # 1. Admin creates a Primary Category (no parent_id)
    res1 = await client.post(
        "/api/v1/admin/categories",
        headers=headers,
        json={
            "name": "Men Test Fashion",
            "description": "Men's high quality fashion",
            "display_order": 1,
        }
    )
    assert res1.status_code == 200, res1.text
    primary_cat = res1.json()["category"]
    assert primary_cat["name"] == "Men Test Fashion"
    assert primary_cat["slug"] == "men-test-fashion"
    assert primary_cat["parent_id"] is None
    assert primary_cat["level"] == "primary"
    primary_id = primary_cat["id"]

    # 2. Admin creates a Subcategory under Primary Category
    res2 = await client.post(
        "/api/v1/admin/categories",
        headers=headers,
        json={
            "name": "Outerwear Test",
            "parent_id": primary_id,
            "description": "Jackets, coats, hoodies",
            "display_order": 2,
        }
    )
    assert res2.status_code == 200, res2.text
    sub_cat = res2.json()["category"]
    assert sub_cat["name"] == "Outerwear Test"
    assert sub_cat["slug"] == "outerwear-test"
    assert sub_cat["parent_id"] == primary_id
    assert sub_cat["parent_name"] == "Men Test Fashion"
    assert sub_cat["level"] == "subcategory"
    sub_id = sub_cat["id"]

    # 3. Admin creates a Child Category under Subcategory
    res3 = await client.post(
        "/api/v1/admin/categories",
        headers=headers,
        json={
            "name": "Leather Jackets",
            "parent_id": sub_id,
            "description": "Genuine leather jackets",
            "display_order": 1,
        }
    )
    assert res3.status_code == 200, res3.text
    child_cat = res3.json()["category"]
    assert child_cat["name"] == "Leather Jackets"
    assert child_cat["slug"] == "leather-jackets"
    assert child_cat["parent_id"] == sub_id
    assert child_cat["parent_name"] == "Outerwear Test"
    assert child_cat["level"] == "child"
    child_id = child_cat["id"]

    # 4. Attempt to create a 4th level category (under child category) should be rejected
    res4 = await client.post(
        "/api/v1/admin/categories",
        headers=headers,
        json={
            "name": "Biker Jackets",
            "parent_id": child_id,
        }
    )
    assert res4.status_code == 400
    assert "up to 3 levels" in res4.json()["detail"]

    # 5. List categories and verify metadata
    res_list = await client.get("/api/v1/admin/categories", headers=headers)
    assert res_list.status_code == 200
    categories = res_list.json()["categories"]
    ids = {c["id"] for c in categories}
    assert primary_id in ids
    assert sub_id in ids
    assert child_id in ids

    # 6. Verify public /categories endpoint includes them
    res_pub_roots = await client.get("/api/v1/categories")
    assert res_pub_roots.status_code == 200
    root_names = [c["name"] for c in res_pub_roots.json()]
    assert "Men Test Fashion" in root_names

    res_pub_subs = await client.get(f"/api/v1/categories?parent_id={primary_id}")
    assert res_pub_subs.status_code == 200
    sub_names = [c["name"] for c in res_pub_subs.json()]
    assert "Outerwear Test" in sub_names

    res_pub_children = await client.get(f"/api/v1/categories?parent_id={sub_id}")
    assert res_pub_children.status_code == 200
    child_names = [c["name"] for c in res_pub_children.json()]
    assert "Leather Jackets" in child_names

    # 7. Update category
    res_update = await client.put(
        f"/api/v1/admin/categories/{child_id}",
        headers=headers,
        json={"name": "Premium Leather Jackets"}
    )
    assert res_update.status_code == 200
    assert res_update.json()["category"]["name"] == "Premium Leather Jackets"

    # 8. Delete child category
    res_del = await client.delete(f"/api/v1/admin/categories/{child_id}", headers=headers)
    assert res_del.status_code == 200
