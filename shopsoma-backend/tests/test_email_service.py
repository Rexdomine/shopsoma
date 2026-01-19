from datetime import datetime

import pytest

from app.services.email_service import EmailService


@pytest.mark.asyncio
async def test_send_admin_order_notification_to_multiple_admins(monkeypatch):
    service = EmailService()
    calls = []

    async def fake_send_email(to_email, to_name, subject, html_content, template_params=None):
        calls.append((to_email, to_name, subject))
        return True

    monkeypatch.setattr(service, "send_email", fake_send_email)

    recipients = [
        {"email": "admin1@example.com", "name": "Admin One"},
        {"email": "admin2@example.com", "name": "Admin Two"},
    ]

    result = await service.send_admin_order_notification(
        order_number="SHP-20250101-TEST",
        customer_name="Test Customer",
        customer_email="customer@example.com",
        order_date=datetime(2025, 1, 1, 10, 0),
        items=[
            {
                "product_name": "Sample Item",
                "quantity": 1,
                "price": 1000,
                "subtotal": 1000,
                "variant_details": {"size": "M", "color": "Blue"},
            }
        ],
        subtotal=1000,
        shipping=0,
        tax=0,
        total=1000,
        payment_status="paid",
        shipping_address={
            "full_name": "Test Customer",
            "address_line_1": "1 Test Street",
            "city": "Lagos",
            "state": "Lagos",
            "postal_code": "100001",
            "country": "Nigeria",
            "phone_number": "0000000000",
        },
        recipients=recipients,
    )

    assert result is True
    assert [call[0] for call in calls] == ["admin1@example.com", "admin2@example.com"]


@pytest.mark.asyncio
async def test_send_vendor_new_order_email(monkeypatch):
    service = EmailService()
    calls = []

    async def fake_send_email(to_email, to_name, subject, html_content, template_params=None):
        calls.append((to_email, to_name, subject))
        return True

    monkeypatch.setattr(service, "send_email", fake_send_email)

    result = await service.send_vendor_new_order_email(
        email="vendor@example.com",
        name="Vendor Store",
        order_number="SHP-20250101-TEST",
        order_date=datetime(2025, 1, 1, 10, 0),
        items=[
            {
                "product_title": "Sample Item",
                "quantity": 2,
                "vendor_payout": 8500,
                "variant_details": {"size": "XL", "color": "Green"},
            }
        ],
        total_payout=8500,
        pickup_date=datetime(2025, 1, 3, 10, 0),
    )

    assert result is True
    assert calls[0][0] == "vendor@example.com"
    assert calls[0][1] == "Vendor Store"


@pytest.mark.asyncio
async def test_send_vendor_payout_processed_email(monkeypatch):
    service = EmailService()
    calls = []

    async def fake_send_email(to_email, to_name, subject, html_content, template_params=None):
        calls.append((to_email, to_name, subject))
        return True

    monkeypatch.setattr(service, "send_email", fake_send_email)

    result = await service.send_vendor_payout_processed_email(
        email="vendor@example.com",
        name="Vendor Store",
        payout_amount=1200,
        processed_at=datetime(2025, 1, 1, 10, 0),
    )

    assert result is True
    assert calls[0][0] == "vendor@example.com"
    assert calls[0][2] == "Payout Processed"


@pytest.mark.asyncio
async def test_send_vendor_payout_failed_email(monkeypatch):
    service = EmailService()
    calls = []

    async def fake_send_email(to_email, to_name, subject, html_content, template_params=None):
        calls.append((to_email, to_name, subject))
        return True

    monkeypatch.setattr(service, "send_email", fake_send_email)

    result = await service.send_vendor_payout_failed_email(
        email="vendor@example.com",
        name="Vendor Store",
        payout_amount=1200,
        failure_reason="Bank transfer failed",
    )

    assert result is True
    assert calls[0][0] == "vendor@example.com"
    assert calls[0][2] == "Payout Failed"
