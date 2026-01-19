async def test_admin_list_vendors_uses_total_orders(
    client,
    db_session,
    admin_user,
    vendor_user,
):
    vendor = vendor_user["vendor"]
    vendor.total_orders = 7
    await db_session.commit()
    await db_session.refresh(vendor)

    response = await client.get(
        "/api/v1/admin/vendors",
        headers=admin_user["headers"],
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"]
    vendor_item = payload["items"][0]
    assert vendor_item["id"] == str(vendor.id)
    assert vendor_item["total_orders"] == 7


async def test_admin_vendor_detail_includes_user_and_bank_fields(
    client,
    db_session,
    admin_user,
    vendor_user,
):
    vendor = vendor_user["vendor"]
    vendor.bank_name = "Test Bank"
    vendor.bank_account_number = "0123456789"
    vendor.bank_account_name = "Test Vendor"
    await db_session.commit()
    await db_session.refresh(vendor)

    response = await client.get(
        f"/api/v1/admin/vendors/{vendor.id}",
        headers=admin_user["headers"],
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["user"]["email"] == vendor_user["user"].email
    assert payload["user"]["full_name"] == vendor_user["user"].full_name
    assert payload["bank_name"] == "Test Bank"
    assert payload["bank_account_number"] == "0123456789"
    assert payload["bank_account_name"] == "Test Vendor"
