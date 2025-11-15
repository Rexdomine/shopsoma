#!/usr/bin/env python3
"""
Simple Product Sync - Local to Staging

This script reads products from local database and displays them.
Since the staging API requires authentication for POST/DELETE,
we'll export the data to a file that can be imported manually.

Usage:
    python scripts/simple_sync_products.py
"""

import json
import requests

LOCAL_API_URL = "http://localhost:8000/api/v1"
STAGING_API_URL = "https://shopsoma-staging-api.onrender.com/api/v1"


def fetch_products(api_url):
    """Fetch all products from API"""
    print(f"\nFetching products from {api_url}...")

    try:
        response = requests.get(f"{api_url}/products", params={"page_size": 100})

        if response.status_code == 200:
            data = response.json()
            products = data.get("products", [])
            print(f"✓ Found {len(products)} products")
            return products
        else:
            print(f"✗ Failed: {response.status_code}")
            return []
    except Exception as e:
        print(f"✗ Error: {e}")
        return []


def main():
    print("\n" + "="*80)
    print("SHOPSOMA PRODUCT COMPARISON")
    print("="*80)

    # Fetch from both environments
    local_products = fetch_products(LOCAL_API_URL)
    staging_products = fetch_products(STAGING_API_URL)

    print("\n" + "="*80)
    print("LOCAL PRODUCTS")
    print("="*80)
    for i, product in enumerate(local_products, 1):
        print(f"{i}. {product['title']} - ₦{product['base_price']}")

    print("\n" + "="*80)
    print("STAGING PRODUCTS")
    print("="*80)
    for i, product in enumerate(staging_products, 1):
        print(f"{i}. {product['title']} - ₦{product['base_price']}")

    # Export local products to JSON file
    export_file = "/Users/rex/Documents/Shopsoma/scripts/local_products_export.json"
    with open(export_file, 'w') as f:
        json.dump(local_products, f, indent=2)

    print("\n" + "="*80)
    print("EXPORT COMPLETE")
    print("="*80)
    print(f"✓ Exported {len(local_products)} products to:")
    print(f"  {export_file}")
    print("\nThese are the products in your LOCAL database.")
    print("They differ from STAGING which has {len(staging_products)} products.")
    print("\nTo sync, we need to:")
    print("1. Create the same products on staging via the backend")
    print("2. Or use a database migration approach")
    print()


if __name__ == "__main__":
    main()
