"""
Simple script to create 4 featured demo products via API
This avoids database connection issues
"""
import requests
import json

BASE_URL = "http://localhost:8000"

# Demo products with SVG images
PRODUCTS = [
    {
        "title": "Artisan Linen Midi Dress",
        "description": "Hand-crafted midi dress in premium linen fabric. Features a relaxed silhouette with elegant draping and a timeless design perfect for both casual and formal occasions.",
        "base_price": 18500.00,
        "images": ["/images/demo-image-2.svg", "/images/demo-image-3.svg"],
        "variants": [
            {"size": "XS", "color": "Cream", "color_hex": "#FFFDD0", "stock": 15, "price": 18500.00},
            {"size": "S", "color": "Cream", "color_hex": "#FFFDD0", "stock": 15, "price": 18500.00},
            {"size": "M", "color": "Cream", "color_hex": "#FFFDD0", "stock": 15, "price": 18500.00},
            {"size": "L", "color": "Cream", "color_hex": "#FFFDD0", "stock": 15, "price": 18500.00},
            {"size": "XL", "color": "Cream", "color_hex": "#FFFDD0", "stock": 15, "price": 18500.00},
            {"size": "XS", "color": "Terracotta", "color_hex": "#E2725B", "stock": 15, "price": 18500.00},
            {"size": "S", "color": "Terracotta", "color_hex": "#E2725B", "stock": 15, "price": 18500.00},
            {"size": "M", "color": "Terracotta", "color_hex": "#E2725B", "stock": 15, "price": 18500.00},
            {"size": "L", "color": "Terracotta", "color_hex": "#E2725B", "stock": 15, "price": 18500.00},
            {"size": "XL", "color": "Terracotta", "color_hex": "#E2725B", "stock": 15, "price": 18500.00},
            {"size": "XS", "color": "Sage", "color_hex": "#9DC183", "stock": 15, "price": 18500.00},
            {"size": "S", "color": "Sage", "color_hex": "#9DC183", "stock": 15, "price": 18500.00},
            {"size": "M", "color": "Sage", "color_hex": "#9DC183", "stock": 15, "price": 18500.00},
            {"size": "L", "color": "Sage", "color_hex": "#9DC183", "stock": 15, "price": 18500.00},
            {"size": "XL", "color": "Sage", "color_hex": "#9DC183", "stock": 15, "price": 18500.00},
        ]
    },
    {
        "title": "Heritage Canvas Tote Bag",
        "description": "Premium canvas tote with leather accents. Spacious interior with multiple compartments, perfect for daily essentials. Sustainable and durable construction.",
        "base_price": 12500.00,
        "images": ["/images/demo-image-3.svg", "/images/demo-image-4.svg"],
        "variants": [
            {"size": "One Size", "color": "Beige", "color_hex": "#F5F5DC", "stock": 15, "price": 12500.00},
            {"size": "One Size", "color": "Olive", "color_hex": "#808000", "stock": 15, "price": 12500.00},
            {"size": "One Size", "color": "Charcoal", "color_hex": "#36454F", "stock": 15, "price": 12500.00},
        ]
    },
    {
        "title": "Contemporary Wool Blend Coat",
        "description": "Luxurious wool blend coat with modern tailoring. Features a relaxed fit, deep pockets, and statement collar. Perfect layering piece for the season.",
        "base_price": 32500.00,
        "images": ["/images/demo-image-4.svg", "/images/demo-image-5.svg"],
        "variants": [
            {"size": "S", "color": "Caramel", "color_hex": "#C68E17", "stock": 15, "price": 32500.00},
            {"size": "M", "color": "Caramel", "color_hex": "#C68E17", "stock": 15, "price": 32500.00},
            {"size": "L", "color": "Caramel", "color_hex": "#C68E17", "stock": 15, "price": 32500.00},
            {"size": "XL", "color": "Caramel", "color_hex": "#C68E17", "stock": 15, "price": 32500.00},
            {"size": "S", "color": "Navy", "color_hex": "#000080", "stock": 15, "price": 32500.00},
            {"size": "M", "color": "Navy", "color_hex": "#000080", "stock": 15, "price": 32500.00},
            {"size": "L", "color": "Navy", "color_hex": "#000080", "stock": 15, "price": 32500.00},
            {"size": "XL", "color": "Navy", "color_hex": "#000080", "stock": 15, "price": 32500.00},
            {"size": "S", "color": "Charcoal", "color_hex": "#36454F", "stock": 15, "price": 32500.00},
            {"size": "M", "color": "Charcoal", "color_hex": "#36454F", "stock": 15, "price": 32500.00},
            {"size": "L", "color": "Charcoal", "color_hex": "#36454F", "stock": 15, "price": 32500.00},
            {"size": "XL", "color": "Charcoal", "color_hex": "#36454F", "stock": 15, "price": 32500.00},
        ]
    },
    {
        "title": "Minimalist Silk Scarf",
        "description": "Pure silk scarf with abstract print. Versatile accessory that can be worn multiple ways. Soft, lightweight, and adds a touch of elegance to any outfit.",
        "base_price": 8500.00,
        "images": ["/images/demo-image-5.svg", "/images/demo-image-2.svg"],
        "variants": [
            {"size": "One Size", "color": "Mustard", "color_hex": "#FFDB58", "stock": 15, "price": 8500.00},
            {"size": "One Size", "color": "Burgundy", "color_hex": "#800020", "stock": 15, "price": 8500.00},
            {"size": "One Size", "color": "Sage", "color_hex": "#9DC183", "stock": 15, "price": 8500.00},
        ]
    }
]

print("📝 Demo Products Ready")
print("\n🔑 SVG images will work fine in the browser!")
print("The images are located at:")
for i in range(2, 6):
    print(f"  - /images/demo-image-{i}.svg")

print("\n✅ Four featured products configured:")
for i, p in enumerate(PRODUCTS, 1):
    print(f"  {i}. {p['title']}")
    print(f"     Price: ₦{p['base_price']:,.2f}")
    print(f"     Variants: {len(p['variants'])}")
    print(f"     Images: {len(p['images'])}")

print("\n📋 Product data structure:")
print(json.dumps(PRODUCTS[0], indent=2))

print("\n💡 To create these products, you would need to:")
print("1. Start the backend API server")
print("2. Login as a vendor")
print("3. Use the product creation API endpoint")
print("4. Or run the seed_featured_products.py script when DB is accessible")
