"""Rendered Chromium → real FastAPI HTTP → owned PostgreSQL acceptance tests."""

import asyncio
import hashlib
import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from playwright.async_api import expect
from sqlalchemy import text

API = "http://127.0.0.1:8000/api/v1"
WEB = "http://127.0.0.1:5173"
EVIDENCE = Path("/evidence")


async def login(browser, email="admin@test.com", password="AdminPass123"):
    context = await browser.new_context(
        viewport={"width": 1280, "height": 900}, timezone_id="UTC"
    )
    page = await context.new_page()
    await page.goto(WEB + "/login")
    await page.locator("input[type=email]").first.fill(email)
    await page.locator("input[type=password]").fill(password)
    await page.get_by_role("button", name="Login", exact=True).click()
    await page.wait_for_url(re.compile(r".*/admin(?:/.*)?$"))
    return page


async def open_order(page, subject):
    await page.goto(WEB + "/admin/orders/" + subject["order"])
    panel = page.get_by_role("region", name="DHL Shipment Operations")
    await expect(panel).to_be_visible()
    return panel


async def confirm(page, panel, name):
    await panel.get_by_role("button", name=name, exact=True).click()
    dialog = page.get_by_role("dialog")
    await expect(dialog).to_be_visible()
    await dialog.get_by_role("button", name=name, exact=True).click()
    await expect(dialog).not_to_be_visible()


async def detail(subject, admin_user):
    async with httpx.AsyncClient(base_url=API, headers=admin_user["headers"]) as client:
        response = await client.get("/admin/orders/" + subject["order"])
        assert response.status_code == 200
        return response.json()


def financial(data):
    # Compare persisted transaction snapshots, not display rounding.
    fields = (
        "subtotal",
        "shipping_cost",
        "tax",
        "discount",
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
        {key: data.get(key) for key in fields},
        [{key: item.get(key) for key in item_fields} for item in data["items"]],
    )


async def test_zero_ready_packages(browser, make_subject, provider):
    subject = await make_subject(0)
    page = await login(browser)
    panel = await open_order(page, subject)
    await expect(
        panel.get_by_text("No ready hub packages.", exact=True)
    ).to_be_visible()
    await expect(
        panel.get_by_role("button", name="Create DHL shipment", exact=True)
    ).to_be_disabled()
    assert provider["booking_calls"] == 0


async def test_multiple_packages_confirmation_focus_and_cancellation(
    browser, make_subject, provider, admin_user
):
    subject = await make_subject(2)
    page = await login(browser)
    panel = await open_order(page, subject)
    create = panel.get_by_role("button", name="Create DHL shipment", exact=True)
    await expect(create).to_be_disabled()
    await panel.get_by_label("Ready hub package").select_option(subject["packages"][1])
    await create.click()
    dialog = page.get_by_role("dialog")
    await expect(
        dialog.get_by_role("button", name="Cancel", exact=True)
    ).to_be_focused()
    await page.keyboard.press("Shift+Tab")
    await expect(
        dialog.get_by_role("button", name="Create DHL shipment", exact=True)
    ).to_be_focused()
    await page.keyboard.press("Tab")
    await expect(
        dialog.get_by_role("button", name="Cancel", exact=True)
    ).to_be_focused()
    await page.screenshot(path=str(EVIDENCE / "multi-confirmation.png"), full_page=True)
    await page.keyboard.press("Escape")
    await expect(create).to_be_focused()
    assert provider["booking_calls"] == 0
    await confirm(page, panel, "Create DHL shipment")
    await expect(
        panel.get_by_text(
            "DHL shipment created. Review the refreshed shipment record.", exact=True
        )
    ).to_be_visible()
    assert provider["booking_calls"] == 1
    saved = await detail(subject, admin_user)
    assert (
        saved["dhl_operations"]["bookings"][0]["package_id"] == subject["packages"][1]
    )


async def test_four_operations_privacy_and_accounting(
    browser, make_subject, admin_user, db_session, provider, external_effects
):
    # Tracking/handoff legitimately attempt notifications. Exercise actual
    # notification failure handling while delivery always raises before IO.
    external_effects["expect_email_failure"] = True
    subject = await make_subject()
    before = await detail(subject, admin_user)
    page = await login(browser)
    panel = await open_order(page, subject)
    await expect(panel.get_by_label("Ready hub package")).to_have_value(
        subject["packages"][0]
    )
    await confirm(page, panel, "Create DHL shipment")
    await expect(
        panel.get_by_text(
            "DHL shipment created. Review the refreshed shipment record.", exact=True
        )
    ).to_be_visible()
    await page.screenshot(
        path=str(EVIDENCE / "booked.png"), full_page=True, mask=[page.locator("input")]
    )
    booked = await detail(subject, admin_user)
    booking = booked["dhl_operations"]["bookings"][0]
    assert booking["package_id"] == subject["packages"][0]
    async with page.expect_download() as pending:
        await panel.get_by_role("button", name="Download DHL label", exact=True).click()
    download = await pending.value
    content = Path(await download.path()).read_bytes()
    assert content.startswith(b"%PDF-")
    await download.delete()
    await expect(panel.get_by_text("DHL label downloaded.", exact=True)).to_be_visible()
    await page.screenshot(
        path=str(EVIDENCE / "label-downloaded.png"),
        full_page=True,
        mask=[page.locator("input")],
    )
    (EVIDENCE / "label-check.json").write_text(
        json.dumps(
            {
                "pdf": True,
                "sha256": hashlib.sha256(content).hexdigest(),
                "payload_retained": False,
            }
        )
    )
    await confirm(page, panel, "Refresh DHL tracking")
    await expect(
        panel.get_by_text("DHL tracking refreshed.", exact=True)
    ).to_be_visible()
    await page.screenshot(
        path=str(EVIDENCE / "tracking-refreshed.png"),
        full_page=True,
        mask=[page.locator("input")],
    )
    # The real input has minute precision. Wait for the next actual minute so
    # native validation passes and occurrence is after the fresh custody tip.
    await asyncio.sleep(60 - datetime.now(UTC).second + 0.1)
    await panel.get_by_label("Collection time (your local time)").fill(
        datetime.now(UTC).strftime("%Y-%m-%dT%H:%M")
    )
    await panel.get_by_label("Counterparty", exact=True).fill("Synthetic carrier")
    await panel.get_by_label("Private evidence reference", exact=True).fill(
        "synthetic-handoff-reference"
    )
    await panel.get_by_label("Evidence SHA-256", exact=True).fill("a" * 64)
    await confirm(page, panel, "Record DHL handoff")
    await expect(
        panel.get_by_text("Hub-to-DHL handoff recorded.", exact=True)
    ).to_be_visible()
    await page.screenshot(
        path=str(EVIDENCE / "handoff-recorded.png"),
        full_page=True,
        mask=[page.locator("input")],
    )
    after = await detail(subject, admin_user)
    assert after["dhl_operations"]["bookings"][0]["handoff_recorded_at"]
    assert financial(before) == financial(after)
    projected = json.dumps(after["dhl_operations"])
    assert "synthetic-handoff-reference" not in projected
    assert "Synthetic carrier" not in projected
    assert "label_content" not in projected
    storage_private = await page.evaluate(
        "Object.values(localStorage).some(v => v.includes('synthetic-handoff-reference') || v.includes('Synthetic carrier'))"
    )
    assert not storage_private
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
    await expect(
        panel.get_by_text(re.compile("DHL pickup booking is unavailable"))
    ).to_be_visible()


@pytest.mark.parametrize("mode", ["timeout", "unknown"])
async def test_uncertain_outcome_survives_reload(
    browser, make_subject, admin_user, provider, mode
):
    subject = await make_subject()
    provider["mode"] = mode
    page = await login(browser)
    panel = await open_order(page, subject)
    await confirm(page, panel, "Create DHL shipment")
    await expect(
        panel.get_by_text(
            re.compile("Shipment outcome needs review|Operation could not be confirmed")
        )
    ).to_be_visible()
    await page.reload()
    await expect(
        panel.get_by_role("button", name="Create DHL shipment", exact=True)
    ).to_be_disabled()
    await expect(
        panel.get_by_text(re.compile("An unresolved local shipment command"))
    ).to_be_visible()
    saved = await detail(subject, admin_user)
    assert saved["dhl_operations"]["bookings"][0]["classification"] == "unknown"
    assert provider["booking_calls"] == 1


async def test_duplicate_click_and_two_admins(
    browser, make_subject, db_session, provider, admin_user
):
    from app.models.user import User, UserRole
    from app.core.security import get_password_hash

    second = User(
        id=uuid.uuid4(),
        email="second-admin@test.com",
        hashed_password=get_password_hash("AdminPass123"),
        full_name="Synthetic Second Admin",
        role=UserRole.ADMIN,
        email_verified=True,
        is_active=True,
    )
    db_session.add(second)
    await db_session.commit()
    subject = await make_subject()
    first_page = await login(browser)
    second_page = await login(browser, email=second.email)
    first, second_panel = await asyncio.gather(
        open_order(first_page, subject), open_order(second_page, subject)
    )
    await first.get_by_role("button", name="Create DHL shipment", exact=True).click()
    await second_panel.get_by_role(
        "button", name="Create DHL shipment", exact=True
    ).click()
    # Real DOM double clicks plus concurrent independent browser/auth sessions.
    await asyncio.gather(
        first_page.get_by_role("dialog")
        .get_by_role("button", name="Create DHL shipment", exact=True)
        .dblclick(),
        second_page.get_by_role("dialog")
        .get_by_role("button", name="Create DHL shipment", exact=True)
        .click(),
    )
    await expect(
        first.get_by_text(
            re.compile("DHL shipment created|Operation could not be confirmed")
        )
    ).to_be_visible()
    await expect(
        second_panel.get_by_text(
            re.compile("DHL shipment created|Operation could not be confirmed")
        )
    ).to_be_visible()
    saved = await detail(subject, admin_user)
    assert len(saved["dhl_operations"]["bookings"]) == 1
    assert provider["booking_calls"] == 1


async def test_real_http_roles_cross_order_label_and_moderation(
    browser, make_subject, admin_user, vendor_user, customer_user, provider
):
    subject = await make_subject()
    other = await make_subject()
    page = await login(browser)
    panel = await open_order(page, subject)
    await confirm(page, panel, "Create DHL shipment")
    await expect(
        panel.get_by_text(
            "DHL shipment created. Review the refreshed shipment record.", exact=True
        )
    ).to_be_visible()
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
