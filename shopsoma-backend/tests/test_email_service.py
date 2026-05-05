from datetime import datetime

import pytest

from app.services.email_service import EmailService


def _capture_email(monkeypatch, service: EmailService):
    calls = []

    async def fake_send_email(
        to_email, to_name, subject, html_content, template_params=None
    ):
        calls.append(
            {
                "to_email": to_email,
                "to_name": to_name,
                "subject": subject,
                "html_content": html_content,
            }
        )
        return True

    monkeypatch.setattr(service, "send_email", fake_send_email)
    return calls


@pytest.mark.asyncio
async def test_send_admin_order_notification_to_multiple_admins(monkeypatch):
    service = EmailService()
    calls = _capture_email(monkeypatch, service)

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
                "currency": "NGN",
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
    assert [call["to_email"] for call in calls] == [
        "admin1@example.com",
        "admin2@example.com",
    ]


@pytest.mark.asyncio
async def test_send_admin_order_notification_formats_usd_amounts(monkeypatch):
    service = EmailService()
    calls = _capture_email(monkeypatch, service)

    result = await service.send_admin_order_notification(
        order_number="SHP-USD-ADMIN",
        customer_name="USD Customer",
        customer_email="customer@example.com",
        order_date=datetime(2025, 3, 25, 15, 0),
        items=[
            {
                "product_name": "Ruffled silk-chiffon blouse",
                "quantity": 1,
                "price": 300,
                "currency": "USD",
                "subtotal": 300,
            }
        ],
        subtotal=300,
        shipping=3.45,
        tax=22.76,
        total=326.21,
        payment_status="paid",
        shipping_address={
            "full_name": "USD Customer",
            "address_line_1": "1 Test Street",
            "city": "Abuja",
            "state": "FCT",
            "postal_code": "900001",
            "country": "Nigeria",
            "phone_number": "0000000000",
        },
        recipients=[{"email": "admin@example.com", "name": "Admin"}],
    )

    assert result is True
    html = calls[0]["html_content"]
    assert "$300.00" in html
    assert "$326.21" in html
    assert "₦300.00" not in html


@pytest.mark.asyncio
async def test_send_order_confirmation_email_formats_usd_amounts(monkeypatch):
    service = EmailService()
    calls = _capture_email(monkeypatch, service)

    result = await service.send_order_confirmation_email(
        email="customer@example.com",
        name="Customer",
        order_number="SHP-USD-TEST",
        order_date=datetime(2025, 1, 1, 10, 0),
        items=[
            {
                "product_name": "Silk Dress",
                "quantity": 1,
                "price": 300,
                "currency": "USD",
                "subtotal": 300,
            }
        ],
        subtotal=300,
        shipping=20,
        tax=24,
        total=344,
        shipping_address={
            "full_name": "Customer",
            "address_line_1": "1 Test Street",
            "city": "New York",
            "state": "NY",
            "postal_code": "10001",
            "country": "USA",
            "phone_number": "0000000000",
        },
    )

    assert result is True
    assert calls[0]["subject"] == "Order Confirmation · SHP-USD-TEST"
    html = calls[0]["html_content"]
    assert "Our artisans and logistics partners are preparing your pieces" in html
    assert "Payment Status:</strong> Payment confirmed" in html
    assert "$300.00" in html
    assert "$344.00" in html
    assert "₦300.00" not in html


@pytest.mark.asyncio
async def test_send_order_confirmation_email_marks_pending_payment_clearly(monkeypatch):
    service = EmailService()
    calls = _capture_email(monkeypatch, service)

    result = await service.send_order_confirmation_email(
        email="customer@example.com",
        name="Customer",
        order_number="SHP-PENDING-TEST",
        order_date=datetime(2025, 1, 1, 10, 0),
        items=[
            {
                "product_name": "Silk Dress",
                "quantity": 1,
                "price": 300,
                "currency": "USD",
                "subtotal": 300,
            }
        ],
        subtotal=300,
        shipping=20,
        tax=24,
        total=344,
        shipping_address={
            "full_name": "Customer",
            "address_line_1": "1 Test Street",
            "city": "New York",
            "state": "NY",
            "postal_code": "10001",
            "country": "USA",
            "phone_number": "0000000000",
        },
        payment_status="PENDING",
    )

    assert result is True
    assert calls[0]["subject"] == "Payment Pending · SHP-PENDING-TEST"
    html = calls[0]["html_content"]
    assert "Payment Pending" in html
    assert "payment is not complete yet" in html
    assert "Payment Status:</strong> Payment pending" in html
    assert "Our artisans and logistics partners are preparing your pieces" not in html


@pytest.mark.asyncio
async def test_send_order_confirmation_email_marks_failed_payment_clearly(monkeypatch):
    service = EmailService()
    calls = _capture_email(monkeypatch, service)

    result = await service.send_order_confirmation_email(
        email="customer@example.com",
        name="Customer",
        order_number="SHP-FAILED-TEST",
        order_date=datetime(2025, 1, 1, 10, 0),
        items=[
            {
                "product_name": "Silk Dress",
                "quantity": 1,
                "price": 300,
                "currency": "USD",
                "subtotal": 300,
            }
        ],
        subtotal=300,
        shipping=20,
        tax=24,
        total=344,
        shipping_address={
            "full_name": "Customer",
            "address_line_1": "1 Test Street",
            "city": "New York",
            "state": "NY",
            "postal_code": "10001",
            "country": "USA",
            "phone_number": "0000000000",
        },
        payment_status="FAILED",
    )

    assert result is True
    assert calls[0]["subject"] == "Payment Failed · SHP-FAILED-TEST"
    html = calls[0]["html_content"]
    assert "Payment Not Completed" in html
    assert "payment did not go through" in html
    assert "Your order is not confirmed until payment is completed" in html
    assert "Payment Status:</strong> Payment failed" in html
    assert "Our artisans and logistics partners are preparing your pieces" not in html


@pytest.mark.asyncio
async def test_send_order_confirmation_email_separates_mixed_currency_totals(
    monkeypatch,
):
    service = EmailService()
    calls = _capture_email(monkeypatch, service)

    result = await service.send_order_confirmation_email(
        email="customer@example.com",
        name="Customer",
        order_number="SHP-MIXED-TEST",
        order_date=datetime(2025, 1, 1, 10, 0),
        items=[
            {
                "product_name": "Kaftan",
                "quantity": 1,
                "price": 60000,
                "currency": "NGN",
                "subtotal": 60000,
            },
            {
                "product_name": "Blouse",
                "quantity": 1,
                "price": 300,
                "currency": "USD",
                "subtotal": 300,
            },
        ],
        subtotal=60300,
        shipping=0,
        tax=0,
        total=60300,
        shipping_address={
            "full_name": "Customer",
            "address_line_1": "1 Test Street",
            "city": "Lagos",
            "state": "Lagos",
            "postal_code": "100001",
            "country": "Nigeria",
            "phone_number": "0000000000",
        },
    )

    assert result is True
    html = calls[0]["html_content"]
    assert "Currency Totals" in html
    assert "NGN Items Total" in html
    assert "USD Items Total" in html
    assert "Shipping, tax, and final total are not combined" in html
    assert ">Total</td>" not in html


@pytest.mark.asyncio
async def test_send_payment_receipt_email_uses_payment_currency(monkeypatch):
    service = EmailService()
    calls = _capture_email(monkeypatch, service)

    result = await service.send_payment_receipt_email(
        email="customer@example.com",
        name="Customer",
        order_number="SHP-USD-RECEIPT",
        amount=300,
        payment_method="Stripe",
        reference="pi_test_123",
        currency="USD",
    )

    assert result is True
    html = calls[0]["html_content"]
    assert "$300.00" in html
    assert "₦300.00" not in html


@pytest.mark.asyncio
async def test_send_vendor_new_order_email(monkeypatch):
    service = EmailService()
    calls = _capture_email(monkeypatch, service)

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
    assert calls[0]["to_email"] == "vendor@example.com"
    assert calls[0]["to_name"] == "Vendor Store"


@pytest.mark.asyncio
async def test_send_vendor_new_order_email_uses_order_currency(monkeypatch):
    service = EmailService()
    calls = _capture_email(monkeypatch, service)

    result = await service.send_vendor_new_order_email(
        email="vendor@example.com",
        name="Vendor Store",
        order_number="SHP-20250325-USD",
        order_date=datetime(2025, 3, 25, 15, 0),
        items=[
            {
                "product_title": "Ruffled silk-chiffon blouse",
                "quantity": 1,
                "vendor_payout": 255,
                "currency": "USD",
                "variant_details": {"color": "green"},
            }
        ],
        total_payout=255,
        pickup_date=datetime(2025, 3, 27, 15, 0),
        currency="USD",
    )

    assert result is True
    html = calls[0]["html_content"]
    assert "$255.00" in html
    assert "₦255.00" not in html


@pytest.mark.asyncio
async def test_send_vendor_payout_processed_email(monkeypatch):
    service = EmailService()
    calls = _capture_email(monkeypatch, service)

    result = await service.send_vendor_payout_processed_email(
        email="vendor@example.com",
        name="Vendor Store",
        payout_amount=1200,
        processed_at=datetime(2025, 1, 1, 10, 0),
    )

    assert result is True
    assert calls[0]["to_email"] == "vendor@example.com"
    assert calls[0]["subject"] == "Payout Processed"


@pytest.mark.asyncio
async def test_send_vendor_payout_failed_email(monkeypatch):
    service = EmailService()
    calls = _capture_email(monkeypatch, service)

    result = await service.send_vendor_payout_failed_email(
        email="vendor@example.com",
        name="Vendor Store",
        payout_amount=1200,
        failure_reason="Bank transfer failed",
    )

    assert result is True
    assert calls[0]["to_email"] == "vendor@example.com"
    assert calls[0]["subject"] == "Payout Failed"
