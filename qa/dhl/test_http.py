"""Real loopback HTTP/auth and owned PostgreSQL integration; no UI execution."""

import hashlib
import json
import uuid
from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy import text

API = "http://127.0.0.1:8000/api/v1"


async def detail(subject, admin_user):
    async with httpx.AsyncClient(base_url=API, headers=admin_user["headers"]) as client:
        response = await client.get("/admin/orders/" + subject["order"])
        assert response.status_code == 200
        return response.json()


async def book(subject, admin_user, index=0):
    saved = await detail(subject, admin_user)
    package = saved["dhl_operations"]["packages"][index]
    payload = {
        key: package[key]
        for key in ("intent_id", "package_id", "package_version", "seal_id")
    }
    payload["idempotency_key"] = str(uuid.uuid4())
    async with httpx.AsyncClient(base_url=API, headers=admin_user["headers"]) as client:
        response = await client.post(
            f"/admin/orders/{subject['order']}/dhl/bookings", json=payload
        )
        assert response.status_code == 200
        return response


def financial(data):
    # Compare persisted transaction snapshots, not display rounding.
    fields = (
        "subtotal",
        "shipping_cost",
        "tax_amount",
        "discount_amount",
        "total_amount",
        "currency",
        "payment_status",
    )
    item_fields = (
        "unit_price",
        "quantity",
        "subtotal",
        "commission_rate",
        "commission_amount",
        "vendor_payout",
        "currency",
    )
    return (
        {key: data[key] for key in fields},
        [{key: item[key] for key in item_fields} for item in data["items"]],
    )


@pytest.mark.parametrize("count", [0, 1, 2])
async def test_ready_package_projection(make_subject, admin_user, provider, count):
    subject = await make_subject(count)
    saved = await detail(subject, admin_user)
    assert len(saved["dhl_operations"]["packages"]) == count
    assert provider["booking_calls"] == 0
    if count:
        await book(subject, admin_user, index=count - 1)
        after = await detail(subject, admin_user)
        assert (
            after["dhl_operations"]["bookings"][0]["package_id"]
            == saved["dhl_operations"]["packages"][count - 1]["package_id"]
        )


async def test_four_operations_privacy_and_accounting(
    make_subject, admin_user, db_session, provider, external_effects
):
    external_effects["expect_email_failure"] = True
    subject = await make_subject()
    before = await detail(subject, admin_user)
    # Obtain authentication through the actual login endpoint, not an auth override.
    async with httpx.AsyncClient(base_url=API) as client:
        login = await client.post(
            "/auth/login", json={"email": "admin@test.com", "password": "AdminPass123"}
        )
        assert login.status_code == 200
        authenticated = {
            "headers": {"Authorization": "Bearer " + login.json()["access_token"]}
        }
    await book(subject, authenticated)
    saved = await detail(subject, authenticated)
    booking = saved["dhl_operations"]["bookings"][0]["booking_id"]
    prefix = f"/admin/orders/{subject['order']}"
    async with httpx.AsyncClient(
        base_url=API, headers=authenticated["headers"]
    ) as client:
        label = await client.get(prefix + f"/dhl/bookings/{booking}/label")
        assert label.status_code == 200
        assert label.content.startswith(b"%PDF-")
        assert (
            label.headers["x-label-sha256"] == hashlib.sha256(label.content).hexdigest()
        )
        tracking = await client.post(
            prefix + "/dhl/tracking-refresh",
            json={"booking_id": booking, "idempotency_key": str(uuid.uuid4())},
        )
        assert tracking.status_code == 200
        handoff = await client.post(
            prefix + f"/dhl/bookings/{booking}/handoff",
            json={
                "occurred_at": datetime.now(UTC).isoformat(),
                "counterparty": "Synthetic carrier",
                "evidence_ref": "synthetic-handoff-reference",
                "evidence_sha256": "a" * 64,
                "idempotency_key": str(uuid.uuid4()),
            },
        )
        assert handoff.status_code == 200
    after = await detail(subject, authenticated)
    assert after["dhl_operations"]["bookings"][0]["handoff_recorded_at"]
    assert financial(before) == financial(after)
    projected = json.dumps(after["dhl_operations"])
    for private in (
        "synthetic-handoff-reference",
        "Synthetic carrier",
        "label_content",
    ):
        assert private not in projected
    assert provider["booking_calls"] == 1
    assert provider["tracking_calls"] == 1
    events = (
        (
            await db_session.execute(
                text(
                    "SELECT event_type FROM custody_events WHERE order_id=:order ORDER BY version"
                ),
                {"order": subject["order"]},
            )
        )
        .scalars()
        .all()
    )
    assert "tendered" in events and "provider_accepted" in events


@pytest.mark.parametrize("mode", ["timeout", "unknown"])
async def test_uncertain_outcome_persists(make_subject, admin_user, provider, mode):
    subject = await make_subject()
    provider["mode"] = mode
    await book(subject, admin_user)
    saved = await detail(subject, admin_user)
    assert saved["dhl_operations"]["bookings"][0]["classification"] == "unknown"
    assert provider["booking_calls"] == 1


async def test_real_http_roles_cross_order_label_and_moderation(
    make_subject, admin_user, vendor_user, customer_user, provider
):
    subject = await make_subject()
    other = await make_subject()
    await book(subject, admin_user)
    saved = await detail(subject, admin_user)
    booking = saved["dhl_operations"]["bookings"][0]["booking_id"]
    package = saved["dhl_operations"]["packages"][0]
    payload = {
        key: package[key]
        for key in ("intent_id", "package_id", "package_version", "seal_id")
    }
    payload["idempotency_key"] = str(uuid.uuid4())
    async with httpx.AsyncClient(base_url=API) as client:
        for headers in ({}, customer_user["headers"], vendor_user["headers"]):
            prefix = "/admin/orders/" + subject["order"]
            checks = [
                await client.get(prefix, headers=headers),
                await client.get(
                    prefix + f"/dhl/bookings/{booking}/label", headers=headers
                ),
                await client.post(
                    prefix + "/dhl/bookings", headers=headers, json=payload
                ),
                await client.post(
                    prefix + f"/dhl/bookings/{booking}/handoff",
                    headers=headers,
                    json={
                        "occurred_at": datetime.now(UTC).isoformat(),
                        "counterparty": "Synthetic",
                        "evidence_ref": "synthetic",
                        "evidence_sha256": "b" * 64,
                        "idempotency_key": str(uuid.uuid4()),
                    },
                ),
                await client.post(
                    prefix + "/dhl/tracking-refresh",
                    headers=headers,
                    json={"booking_id": booking, "idempotency_key": str(uuid.uuid4())},
                ),
            ]
            assert all(response.status_code in (401, 403) for response in checks)
        wrong_label = await client.get(
            f"/admin/orders/{other['order']}/dhl/bookings/{booking}/label",
            headers=admin_user["headers"],
        )
        assert wrong_label.status_code == 404
        wrong_book = await client.post(
            f"/admin/orders/{other['order']}/dhl/bookings",
            headers=admin_user["headers"],
            json=payload,
        )
        assert wrong_book.status_code in (400, 404, 409)
        # Fixture graph creates a pending product. Customer detail must stay private.
        product_id = str(subject["graph"]["item"].product_id)
        pending = await client.get(
            "/products/" + product_id, headers=customer_user["headers"]
        )
        assert pending.status_code == 404
    assert provider["booking_calls"] == 1
