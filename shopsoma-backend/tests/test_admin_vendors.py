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
