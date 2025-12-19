"""
Test script for ShipBubble integration

Run this to verify ShipBubble API is working correctly
"""
import asyncio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.shipbubble_service import ShipBubbleService, ShipBubbleError


async def test_shipbubble_integration():
    """Test ShipBubble API integration"""

    print("=" * 60)
    print("SHIPBUBBLE INTEGRATION TEST")
    print("=" * 60)

    try:
        # Initialize service
        print("\n1️⃣ Initializing ShipBubble service...")
        service = ShipBubbleService()
        print("   ✅ Service initialized successfully")

    except ValueError as e:
        print(f"   ❌ Configuration error: {e}")
        print("\n💡 Make sure SHIPBUBBLE_API_KEY is set in .env file")
        return

    except Exception as e:
        print(f"   ❌ Initialization failed: {e}")
        return

    # Test 1: Create Addresses
    print("\n2️⃣ Testing: Create Addresses")
    print("-" * 60)

    try:
        print("   Creating sender address...")
        sender_code = await service.create_address(
            name="Kester Club",
            phone="+2348012345678",
            email="vendor@shopsoma.com",
            address="123 Vendor Street, Gwarinpa",
            city="Abuja",
            state="FCT",
            country="Nigeria",
            postal_code="900211"
        )
        print(f"   ✅ Sender address created: Code {sender_code}")

        print("   Creating receiver address...")
        receiver_code = await service.create_address(
            name="John Customer",
            phone="+2348087654321",
            email="customer@example.com",
            address="456 Customer Avenue, Lekki",
            city="Lagos",
            state="Lagos",
            country="Nigeria",
            postal_code="101245"
        )
        print(f"   ✅ Receiver address created: Code {receiver_code}")

    except ShipBubbleError as e:
        print(f"   ❌ API Error: {e.message}")
        if e.status_code:
            print(f"   Status Code: {e.status_code}")
        if e.response_data:
            print(f"   Response: {e.response_data}")
        print("\n💡 Cannot proceed without addresses")
        return
    except Exception as e:
        print(f"   ❌ Unexpected error: {e}")
        return

    # Test 2: Get Shipping Rates
    print("\n3️⃣ Testing: Get Shipping Rates")
    print("-" * 60)

    try:
        from datetime import datetime, timedelta
        pickup_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

        rates = await service.get_shipping_rates(
            sender_address_code=sender_code,
            receiver_address_code=receiver_code,
            pickup_date=pickup_date,
            category_id=1,  # Default category - adjust based on your ShipBubble account
            package_items=[
                {
                    "name": "T-Shirt",
                    "description": "Cotton T-Shirt Size M",
                    "unit_weight": 0.5,  # kg
                    "unit_amount": 5000,  # NGN
                    "quantity": 2
                },
                {
                    "name": "Jeans",
                    "description": "Denim Jeans Size 32",
                    "unit_weight": 0.7,  # kg
                    "unit_amount": 8000,  # NGN
                    "quantity": 1
                }
            ],
            package_dimension={
                "length": 30,  # cm
                "width": 25,   # cm
                "height": 10   # cm
            },
            service_type="pickup"
        )

        if rates:
            print(f"   ✅ Retrieved {len(rates)} shipping rate(s):")
            for i, rate in enumerate(rates, 1):
                print(f"\n   Option {i}:")
                print(f"      Courier: {rate['courier']}")
                print(f"      Price: ₦{rate['price']:,.2f}")
                print(f"      Delivery: {rate['estimated_days']} day(s)")
                print(f"      Service: {rate['service_code']}")
        else:
            print("   ⚠️ No rates returned (check API response format)")
            print("   💡 This might be normal if API structure is different")

    except ShipBubbleError as e:
        print(f"   ❌ API Error: {e.message}")
        if e.status_code:
            print(f"   Status Code: {e.status_code}")
        if e.response_data:
            print(f"   Response: {e.response_data}")
    except Exception as e:
        print(f"   ❌ Unexpected error: {e}")

    # Test 3: Create Shipment
    print("\n4️⃣ Testing: Create Shipment")
    print("-" * 60)
    print("   ⚠️ Skipping shipment creation in test")
    print("   💡 To test, uncomment the code below")

    # Uncomment to test shipment creation:
    # try:
    #     shipment = await service.create_shipment(
    #         order_number="TEST-ORDER-001",
    #         sender={
    #             "name": "Kester Club",
    #             "phone": "+2348012345678",
    #             "email": "vendor@shopsoma.com",
    #             **sender_address
    #         },
    #         receiver={
    #             "name": "John Customer",
    #             "phone": "+2348087654321",
    #             "email": "customer@example.com",
    #             **receiver_address
    #         },
    #         items=[
    #             {
    #                 "name": "T-Shirt",
    #                 "quantity": 2,
    #                 "value": 5000,
    #                 "weight": 0.5,
    #                 "description": "Cotton T-Shirt Size M"
    #             }
    #         ],
    #         service_code="dhl_express"  # Use service_code from rates response
    #     )
    #
    #     print(f"   ✅ Shipment created successfully:")
    #     print(f"      Shipment ID: {shipment['shipment_id']}")
    #     print(f"      Tracking: {shipment.get('tracking_number')}")
    #     print(f"      Status: {shipment.get('status')}")
    #
    # except ShipBubbleError as e:
    #     print(f"   ❌ API Error: {e.message}")
    #     if e.response_data:
    #         print(f"   Response: {e.response_data}")

    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)
    print("\n💡 Next Steps:")
    print("   1. Check the logs above for any errors")
    print("   2. If rates returned successfully, ShipBubble is working!")
    print("   3. Update _parse_rates_response() if response format differs")
    print("   4. Uncomment shipment creation test when ready")
    print()


if __name__ == "__main__":
    asyncio.run(test_shipbubble_integration())
