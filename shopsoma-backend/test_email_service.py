"""
Test script for Brevo email service integration
"""
import asyncio
from datetime import datetime
from app.services.email_service import email_service


async def test_welcome_email():
    """Test welcome email"""
    print("\n📧 Testing Welcome Email...")
    result = await email_service.send_welcome_email(
        email="test@example.com",
        name="Test User"
    )
    if result:
        print("✅ Welcome email sent successfully!")
    else:
        print("❌ Failed to send welcome email")
    return result


async def test_order_confirmation_email():
    """Test order confirmation email"""
    print("\n📧 Testing Order Confirmation Email...")

    # Sample order data
    items = [
        {
            'product_name': 'Classic White T-Shirt',
            'quantity': 2,
            'price': 15000.00,
            'subtotal': 30000.00,
            'size': 'L',
            'color': 'White'
        },
        {
            'product_name': 'Denim Jeans',
            'quantity': 1,
            'price': 45000.00,
            'subtotal': 45000.00,
            'size': '32',
            'color': 'Blue'
        }
    ]

    shipping_address = {
        'full_name': 'John Doe',
        'address_line_1': '123 Victoria Island',
        'address_line_2': 'Apartment 4B',
        'city': 'Lagos',
        'state': 'Lagos',
        'postal_code': '100001',
        'country': 'Nigeria',
        'phone_number': '+234 801 234 5678'
    }

    result = await email_service.send_order_confirmation_email(
        email="test@example.com",
        name="John Doe",
        order_number="SHP-20251119-ABC123",
        order_date=datetime.now(),
        items=items,
        subtotal=75000.00,
        shipping=2000.00,
        tax=5775.00,  # 7.5% VAT
        total=82775.00,
        shipping_address=shipping_address
    )

    if result:
        print("✅ Order confirmation email sent successfully!")
    else:
        print("❌ Failed to send order confirmation email")
    return result


async def test_payment_receipt_email():
    """Test payment receipt email"""
    print("\n📧 Testing Payment Receipt Email...")

    result = await email_service.send_payment_receipt_email(
        email="test@example.com",
        name="John Doe",
        order_number="SHP-20251119-ABC123",
        amount=82775.00,
        payment_method="Stripe",
        reference="pi_3QRsT1uvW2xY3zA4B5cD6eF7"
    )

    if result:
        print("✅ Payment receipt email sent successfully!")
    else:
        print("❌ Failed to send payment receipt email")
    return result


async def test_order_status_update_email():
    """Test order status update email"""
    print("\n📧 Testing Order Status Update Email...")

    # Test different statuses
    statuses = [
        ("processing", None),
        ("shipped", "TRK123456789NG"),
        ("delivered", None)
    ]

    results = []
    for status_type, tracking in statuses:
        print(f"  Testing '{status_type}' status...")
        result = await email_service.send_order_status_update_email(
            email="test@example.com",
            name="John Doe",
            order_number="SHP-20251119-ABC123",
            status=status_type,
            tracking_number=tracking
        )
        results.append(result)
        if result:
            print(f"  ✅ {status_type.title()} email sent successfully!")
        else:
            print(f"  ❌ Failed to send {status_type} email")

    return all(results)


async def run_all_tests():
    """Run all email tests"""
    print("=" * 60)
    print("🧪 BREVO EMAIL SERVICE TEST SUITE")
    print("=" * 60)

    results = {}

    # Test 1: Welcome Email
    results['welcome'] = await test_welcome_email()

    # Test 2: Order Confirmation
    results['order_confirmation'] = await test_order_confirmation_email()

    # Test 3: Payment Receipt
    results['payment_receipt'] = await test_payment_receipt_email()

    # Test 4: Order Status Updates
    results['status_updates'] = await test_order_status_update_email()

    # Summary
    print("\n" + "=" * 60)
    print("📊 TEST SUMMARY")
    print("=" * 60)
    total_tests = len(results)
    passed_tests = sum(1 for result in results.values() if result)

    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{test_name.replace('_', ' ').title()}: {status}")

    print(f"\nTotal: {passed_tests}/{total_tests} tests passed")

    if passed_tests == total_tests:
        print("\n🎉 All email tests passed! Brevo integration is working correctly.")
    else:
        print(f"\n⚠️  {total_tests - passed_tests} test(s) failed. Please check your Brevo API key and configuration.")

    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_all_tests())
