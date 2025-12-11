#!/usr/bin/env python3
"""
Test script for product variations API
Run with: python test_variations_api.py
"""
import requests
import json

# Configuration
BASE_URL = "http://localhost:8000/api/v1"
VENDOR_EMAIL = "vendor@shopsoma.com"
VENDOR_PASSWORD = "vendor123"  # Update with actual password

def login_vendor():
    """Login as vendor and get access token"""
    response = requests.post(
        f"{BASE_URL}/auth/login",
        json={
            "email": VENDOR_EMAIL,
            "password": VENDOR_PASSWORD
        }
    )
    if response.status_code != 200:
        print(f"Login failed: {response.status_code}")
        print(response.text)
        return None

    data = response.json()
    return data.get("access_token")

def create_product_with_variations(token):
    """Create a product with variations"""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    product_data = {
        "title": "Test Product with Variations",
        "description": "A test product with multiple color variations and sizes",
        "base_price": 50.00,
        "compare_at_price": 75.00,
        "status": "draft",
        "is_featured": False,
        "variations": [
            {
                "title": "Black",
                "type": "color",
                "color_hex": "#000000",
                "price": None,  # Use base price
                "sale_price": None,
                "images": ["https://example.com/black-1.jpg", "https://example.com/black-2.jpg"],
                "is_active": True,
                "sizes": [
                    {"size": "S", "stock": 10},
                    {"size": "M", "stock": 15},
                    {"size": "L", "stock": 20},
                    {"size": "XL", "stock": 5}
                ]
            },
            {
                "title": "Red",
                "type": "color",
                "color_hex": "#FF0000",
                "price": 55.00,  # Different pricing
                "sale_price": None,
                "images": ["https://example.com/red-1.jpg"],
                "is_active": True,
                "sizes": [
                    {"size": "S", "stock": 8},
                    {"size": "M", "stock": 12},
                    {"size": "L", "stock": 18}
                ]
            },
            {
                "title": "Blue",
                "type": "color",
                "color_hex": "#0000FF",
                "price": None,
                "sale_price": None,
                "images": ["https://example.com/blue-1.jpg", "https://example.com/blue-2.jpg", "https://example.com/blue-3.jpg"],
                "is_active": True,
                "sizes": [
                    {"size": "XS", "stock": 5},
                    {"size": "S", "stock": 10},
                    {"size": "M", "stock": 15},
                    {"size": "L", "stock": 10},
                    {"size": "XL", "stock": 8},
                    {"size": "XXL", "stock": 3}
                ]
            }
        ]
    }

    response = requests.post(
        f"{BASE_URL}/products",
        headers=headers,
        json=product_data
    )

    if response.status_code != 201:
        print(f"Create product failed: {response.status_code}")
        print(response.text)
        return None

    return response.json()

def get_product(product_id, token):
    """Get product with variations"""
    headers = {
        "Authorization": f"Bearer {token}"
    }

    response = requests.get(
        f"{BASE_URL}/products/{product_id}",
        headers=headers
    )

    if response.status_code != 200:
        print(f"Get product failed: {response.status_code}")
        print(response.text)
        return None

    return response.json()

def main():
    print("🧪 Testing Product Variations API\n")

    # Login
    print("1️⃣ Logging in as vendor...")
    token = login_vendor()
    if not token:
        print("❌ Login failed. Update VENDOR_EMAIL and VENDOR_PASSWORD in the script.")
        return
    print("✅ Logged in successfully\n")

    # Create product with variations
    print("2️⃣ Creating product with variations...")
    product = create_product_with_variations(token)
    if not product:
        print("❌ Failed to create product")
        return

    print(f"✅ Product created with ID: {product['id']}")
    print(f"   - Title: {product['title']}")
    print(f"   - Variations: {len(product.get('variations', []))}")

    # Display variations
    if product.get('variations'):
        print("\n   Variations:")
        for var in product['variations']:
            print(f"     • {var['title']} ({var['color_hex']}) - {len(var['size_stocks'])} sizes")
            for size in var['size_stocks']:
                print(f"       - {size['size']}: {size['stock']} units")

    print("\n3️⃣ Fetching product to verify...")
    fetched_product = get_product(product['id'], token)
    if not fetched_product:
        print("❌ Failed to fetch product")
        return

    print("✅ Product fetched successfully")
    print(f"   - Has {len(fetched_product.get('variations', []))} variations")
    print(f"   - Total size stocks: {sum(len(v['size_stocks']) for v in fetched_product.get('variations', []))}")

    print("\n🎉 All tests passed!")
    print(f"\n📦 Test Product ID: {product['id']}")
    print("You can now view this product in the frontend or use the ID for further testing.")

if __name__ == "__main__":
    main()
