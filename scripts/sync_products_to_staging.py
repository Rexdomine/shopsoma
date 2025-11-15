#!/usr/bin/env python3
"""
Sync Products from Local to Staging

This script exports products from the local database and imports them to staging.
It uses the API to ensure proper validation and consistency.

Usage:
    python scripts/sync_products_to_staging.py
"""

import os
import sys
import json
import requests
from typing import List, Dict, Any, Optional

# Configuration
LOCAL_API_URL = "http://localhost:8000/api/v1"
STAGING_API_URL = "https://shopsoma-staging-api.onrender.com/api/v1"

# These should be your vendor credentials
# You can set these as environment variables or replace with actual values
LOCAL_EMAIL = os.getenv("LOCAL_VENDOR_EMAIL", "vendor@example.com")
LOCAL_PASSWORD = os.getenv("LOCAL_VENDOR_PASSWORD", "password123")

STAGING_EMAIL = os.getenv("STAGING_VENDOR_EMAIL", "vendor@example.com")
STAGING_PASSWORD = os.getenv("STAGING_VENDOR_PASSWORD", "password123")


class ProductSyncService:
    def __init__(self):
        self.local_token: Optional[str] = None
        self.staging_token: Optional[str] = None
        self.local_vendor_id: Optional[str] = None
        self.staging_vendor_id: Optional[str] = None

    def authenticate(self, api_url: str, email: str, password: str) -> Dict[str, Any]:
        """Authenticate and get access token"""
        print(f"Authenticating with {api_url}...")

        try:
            response = requests.post(
                f"{api_url}/auth/login",
                json={"email": email, "password": password},
                headers={"Content-Type": "application/json"}
            )

            if response.status_code == 200:
                data = response.json()
                print(f"✓ Authentication successful")
                return data
            else:
                print(f"✗ Authentication failed: {response.status_code}")
                print(f"Response: {response.text}")
                return None
        except Exception as e:
            print(f"✗ Authentication error: {e}")
            return None

    def get_products(self, api_url: str, token: str) -> List[Dict[str, Any]]:
        """Fetch all products from API"""
        print(f"Fetching products from {api_url}...")

        try:
            response = requests.get(
                f"{api_url}/products",
                params={"page_size": 100},
                headers={"Authorization": f"Bearer {token}"}
            )

            if response.status_code == 200:
                data = response.json()
                products = data.get("products", [])
                print(f"✓ Found {len(products)} products")
                return products
            else:
                print(f"✗ Failed to fetch products: {response.status_code}")
                return []
        except Exception as e:
            print(f"✗ Error fetching products: {e}")
            return []

    def delete_product(self, api_url: str, token: str, product_id: str) -> bool:
        """Delete a product"""
        try:
            response = requests.delete(
                f"{api_url}/products/{product_id}",
                headers={"Authorization": f"Bearer {token}"}
            )
            return response.status_code in [200, 204]
        except Exception as e:
            print(f"  ✗ Error deleting product: {e}")
            return False

    def create_product(self, api_url: str, token: str, product_data: Dict[str, Any]) -> bool:
        """Create a new product"""
        try:
            # Remove fields that shouldn't be in the create request
            clean_data = {
                "title": product_data["title"],
                "description": product_data.get("description"),
                "base_price": str(product_data["base_price"]),
                "compare_at_price": str(product_data["compare_at_price"]) if product_data.get("compare_at_price") else None,
                "status": product_data.get("status", "active"),
                "is_featured": product_data.get("is_featured", False),
                "size_guide": product_data.get("size_guide"),
                "variants": [],
                "images": []
            }

            # Add variants
            if product_data.get("variants"):
                for variant in product_data["variants"]:
                    clean_data["variants"].append({
                        "size": variant.get("size"),
                        "color": variant.get("color"),
                        "color_hex": variant.get("color_hex"),
                        "price": str(variant["price"]),
                        "stock": variant.get("stock", 0),
                        "sku": variant.get("sku"),
                        "is_available": variant.get("is_available", True)
                    })

            # Add images
            if product_data.get("images"):
                for image in product_data["images"]:
                    clean_data["images"].append({
                        "image_url": image["image_url"],
                        "thumbnail_url": image.get("thumbnail_url", image["image_url"]),
                        "alt_text": image.get("alt_text", product_data["title"]),
                        "display_order": image.get("display_order", 0),
                        "is_primary": image.get("is_primary", False)
                    })

            response = requests.post(
                f"{api_url}/products",
                json=clean_data,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json"
                }
            )

            if response.status_code in [200, 201]:
                return True
            else:
                print(f"  ✗ Failed to create product: {response.status_code}")
                print(f"  Response: {response.text}")
                return False

        except Exception as e:
            print(f"  ✗ Error creating product: {e}")
            return False

    def sync(self, clear_staging: bool = False):
        """Main sync process"""
        print("\n" + "="*80)
        print("SHOPSOMA PRODUCT SYNC - Local to Staging")
        print("="*80 + "\n")

        # Step 1: Authenticate with local
        print("Step 1: Authenticate with Local API")
        local_auth = self.authenticate(LOCAL_API_URL, LOCAL_EMAIL, LOCAL_PASSWORD)
        if not local_auth:
            print("✗ Failed to authenticate with local API")
            return False

        self.local_token = local_auth["access_token"]
        print()

        # Step 2: Authenticate with staging
        print("Step 2: Authenticate with Staging API")
        staging_auth = self.authenticate(STAGING_API_URL, STAGING_EMAIL, STAGING_PASSWORD)
        if not staging_auth:
            print("✗ Failed to authenticate with staging API")
            return False

        self.staging_token = staging_auth["access_token"]
        print()

        # Step 3: Fetch local products
        print("Step 3: Fetch Local Products")
        local_products = self.get_products(LOCAL_API_URL, self.local_token)
        if not local_products:
            print("✗ No products found in local database")
            return False
        print()

        # Step 4: Optionally clear staging products
        if clear_staging:
            print("Step 4: Clear Staging Products")
            staging_products = self.get_products(STAGING_API_URL, self.staging_token)
            for product in staging_products:
                print(f"  Deleting: {product['title']}")
                self.delete_product(STAGING_API_URL, self.staging_token, product['id'])
            print(f"✓ Cleared {len(staging_products)} products from staging\n")
        else:
            print("Step 4: Skipping staging cleanup (clear_staging=False)\n")

        # Step 5: Create products on staging
        print("Step 5: Create Products on Staging")
        success_count = 0
        fail_count = 0

        for i, product in enumerate(local_products, 1):
            print(f"  [{i}/{len(local_products)}] Creating: {product['title']}")
            if self.create_product(STAGING_API_URL, self.staging_token, product):
                success_count += 1
                print(f"    ✓ Success")
            else:
                fail_count += 1
                print(f"    ✗ Failed")

        print()
        print("="*80)
        print("SYNC COMPLETE")
        print("="*80)
        print(f"Total products: {len(local_products)}")
        print(f"Successfully synced: {success_count}")
        print(f"Failed: {fail_count}")
        print()

        return fail_count == 0


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description="Sync products from local to staging")
    parser.add_argument(
        "--clear-staging",
        action="store_true",
        help="Clear all products from staging before syncing"
    )
    parser.add_argument(
        "--local-email",
        default=LOCAL_EMAIL,
        help="Local vendor email"
    )
    parser.add_argument(
        "--local-password",
        default=LOCAL_PASSWORD,
        help="Local vendor password"
    )
    parser.add_argument(
        "--staging-email",
        default=STAGING_EMAIL,
        help="Staging vendor email"
    )
    parser.add_argument(
        "--staging-password",
        default=STAGING_PASSWORD,
        help="Staging vendor password"
    )

    args = parser.parse_args()

    # Update credentials if provided
    global LOCAL_EMAIL, LOCAL_PASSWORD, STAGING_EMAIL, STAGING_PASSWORD
    LOCAL_EMAIL = args.local_email
    LOCAL_PASSWORD = args.local_password
    STAGING_EMAIL = args.staging_email
    STAGING_PASSWORD = args.staging_password

    # Create sync service and run
    sync_service = ProductSyncService()
    success = sync_service.sync(clear_staging=args.clear_staging)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
