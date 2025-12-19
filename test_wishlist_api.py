"""
Test script to verify wishlist API functionality
"""
import requests
import json

# Configuration
BASE_URL = "http://localhost:8000/api/v1"

# Step 1: Login to get token
print("Step 1: Logging in...")
login_response = requests.post(
    f"{BASE_URL}/auth/login",
    json={
        "email": "rextechng@gmail.com",
        "password": "Sphola24"
    }
)

if login_response.status_code != 200:
    print(f"❌ Login failed: {login_response.status_code}")
    print(login_response.text)
    exit(1)

token = login_response.json()["access_token"]
print(f"✓ Login successful! Token: {token[:20]}...")

headers = {"Authorization": f"Bearer {token}"}

# Step 2: Get a product to add to wishlist
print("\nStep 2: Getting a product...")
products_response = requests.get(f"{BASE_URL}/products", params={"page_size": 1})
if products_response.status_code != 200:
    print(f"❌ Failed to get products: {products_response.status_code}")
    exit(1)

products = products_response.json()["products"]
if not products:
    print("❌ No products found in database")
    exit(1)

product_id = products[0]["id"]
product_title = products[0]["title"]
print(f"✓ Found product: {product_title} (ID: {product_id})")

# Step 3: Add product to wishlist
print("\nStep 3: Adding product to wishlist...")
add_response = requests.post(
    f"{BASE_URL}/wishlist",
    json={"product_id": product_id},
    headers=headers
)

if add_response.status_code == 201:
    print(f"✓ Product added to wishlist!")
    print(json.dumps(add_response.json(), indent=2))
elif add_response.status_code == 400 and "already in wishlist" in add_response.json().get("detail", ""):
    print(f"⚠️  Product already in wishlist")
else:
    print(f"❌ Failed to add to wishlist: {add_response.status_code}")
    print(add_response.text)
    exit(1)

# Step 4: Get wishlist
print("\nStep 4: Getting wishlist...")
wishlist_response = requests.get(f"{BASE_URL}/wishlist", headers=headers)
if wishlist_response.status_code != 200:
    print(f"❌ Failed to get wishlist: {wishlist_response.status_code}")
    print(wishlist_response.text)
    exit(1)

wishlist_data = wishlist_response.json()
print(f"✓ Wishlist contains {wishlist_data['total']} items")
for item in wishlist_data["items"]:
    print(f"  - {item['product_title']}")

# Step 5: Check if product is in wishlist
print("\nStep 5: Checking if product is in wishlist...")
check_response = requests.get(f"{BASE_URL}/wishlist/check/{product_id}", headers=headers)
if check_response.status_code != 200:
    print(f"❌ Failed to check wishlist: {check_response.status_code}")
    exit(1)

check_data = check_response.json()
print(f"✓ Product in wishlist: {check_data['in_wishlist']}")

print("\n✅ All tests passed! Wishlist API is working correctly.")
