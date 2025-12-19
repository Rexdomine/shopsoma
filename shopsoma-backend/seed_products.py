"""
Seed script to create demo fashion products for testing
Run this script to populate the database with sample products
"""
import asyncio
import httpx
from typing import Dict, List
from decimal import Decimal

# API Base URL
BASE_URL = "http://localhost:8000/api/v1"

DEFAULT_COLORS = [
    {"name": "Emerald Green", "hex": "#0F766E"},
    {"name": "Sahara Gold", "hex": "#D97706"},
    {"name": "Onyx Black", "hex": "#111827"},
]

SIZE_OPTIONS = ["L", "XL", "XXL"]

WOMEN_SIZE_ROWS = [
    {"label": "L", "standard": "UK 12 / US 8", "measurement": 'Bust 38" / Waist 30"'},
    {"label": "XL", "standard": "UK 14 / US 10", "measurement": 'Bust 40" / Waist 32"'},
    {"label": "XXL", "standard": "UK 16 / US 12", "measurement": 'Bust 42" / Waist 34"'},
]

MEN_SIZE_ROWS = [
    {"label": "L", "standard": "EU 52 / US 42", "measurement": 'Chest 42" / Waist 36"'},
    {"label": "XL", "standard": "EU 54 / US 44", "measurement": 'Chest 44" / Waist 38"'},
    {"label": "XXL", "standard": "EU 56 / US 46", "measurement": 'Chest 46" / Waist 40"'},
]


def slugify(value: str) -> str:
    return "".join(ch for ch in value.upper() if ch.isalnum()) or "PROD"


def build_size_guide(product_data: Dict) -> Dict:
    gender = product_data.get("size_guide_gender")
    if not gender:
        category = product_data.get("category", "").lower()
        gender = "Men" if "men" in category else "Women"

    template = MEN_SIZE_ROWS if gender.lower().startswith("men") else WOMEN_SIZE_ROWS
    rows = [row.copy() for row in template]

    return {
        "title": f"{gender.title()} Size Guide",
        "subtitle": product_data["title"],
        "gender": gender.title(),
        "rows": rows,
    }


def build_variants(product_data: Dict) -> List[Dict]:
    colors = product_data.get("colors") or DEFAULT_COLORS
    base_price = Decimal(str(product_data["base_price"]))
    slug = slugify(product_data["title"])[:6]
    vendor_code = slugify(product_data["vendor_name"])[:4]
    variants: List[Dict] = []

    for color in colors[:3]:
        color_code = "".join(word[0] for word in color["name"].split()).upper()[:3]
        for size in SIZE_OPTIONS:
            sku = f"{slug}-{vendor_code}-{color_code}-{size}"
            variants.append(
                {
                    "sku": sku,
                    "size": size,
                    "color": color["name"],
                    "color_hex": color.get("hex"),
                    "price": float(base_price),
                    "stock": 40,
                    "is_available": True,
                }
            )
    return variants

# Demo products data
DEMO_PRODUCTS = [
    {
        "title": "Classic Ankara Print Dress",
        "description": "Beautiful handcrafted Ankara print dress with vibrant colors and traditional patterns. Perfect for special occasions and cultural events. Made from 100% cotton fabric with comfortable fit.",
        "category": "Women's Fashion",
        "base_price": 25000,
        "inventory_quantity": 50,
        "vendor_name": "Adaeze Collections",
        "images": [
            "https://images.unsplash.com/photo-1595777457583-95e059d581b8?w=800&h=800&fit=crop",
            "https://images.unsplash.com/photo-1596783074918-c84cb06531ca?w=800&h=800&fit=crop"
        ],
        "variants": [
            {"sku": "ANK-DRS-S-001", "option_name": "Size", "option_value": "Small", "price": 25000, "compare_at_price": 32000, "inventory_quantity": 15},
            {"sku": "ANK-DRS-M-001", "option_name": "Size", "option_value": "Medium", "price": 25000, "compare_at_price": 32000, "inventory_quantity": 20},
            {"sku": "ANK-DRS-L-001", "option_name": "Size", "option_value": "Large", "price": 26000, "compare_at_price": 33000, "inventory_quantity": 15}
        ]
    },
    {
        "title": "Men's Agbada Traditional Outfit",
        "description": "Premium quality Agbada set with intricate embroidery. Includes flowing robe, inner caftan, and matching trousers. Ideal for weddings, ceremonies, and formal events.",
        "category": "Men's Fashion",
        "base_price": 45000,
        "inventory_quantity": 30,
        "vendor_name": "Royal Threads Nigeria",
        "images": [
            "https://images.unsplash.com/photo-1617127365659-c47fa864d8bc?w=800&h=800&fit=crop",
            "https://images.unsplash.com/photo-1622470953794-aa9c70b0fb9d?w=800&h=800&fit=crop"
        ],
        "variants": [
            {"sku": "AGB-SET-M-001", "option_name": "Size", "option_value": "Medium", "price": 45000, "compare_at_price": 55000, "inventory_quantity": 10},
            {"sku": "AGB-SET-L-001", "option_name": "Size", "option_value": "Large", "price": 45000, "compare_at_price": 55000, "inventory_quantity": 12},
            {"sku": "AGB-SET-XL-001", "option_name": "Size", "option_value": "X-Large", "price": 47000, "compare_at_price": 57000, "inventory_quantity": 8}
        ]
    },
    {
        "title": "Elegant Gele Head Wrap Set",
        "description": "Luxurious gele fabric set with matching shoulder wrap. Perfect for completing your traditional outfit. Soft, comfortable, and easy to tie. Available in stunning colors.",
        "category": "Women's Fashion",
        "base_price": 8500,
        "inventory_quantity": 100,
        "vendor_name": "Aso Oke Treasures",
        "images": [
            "https://images.unsplash.com/photo-1611652022419-a9419f74343a?w=800&h=800&fit=crop",
            "https://images.unsplash.com/photo-1600003014755-ba31aa59c4b6?w=800&h=800&fit=crop"
        ],
        "variants": [
            {"sku": "GEL-001-GOLD", "option_name": "Color", "option_value": "Gold", "price": 8500, "compare_at_price": 12000, "inventory_quantity": 30},
            {"sku": "GEL-001-PURPLE", "option_name": "Color", "option_value": "Royal Purple", "price": 8500, "compare_at_price": 12000, "inventory_quantity": 35},
            {"sku": "GEL-001-CORAL", "option_name": "Color", "option_value": "Coral Pink", "price": 9000, "compare_at_price": 12500, "inventory_quantity": 35}
        ]
    },
    {
        "title": "Designer Kaftan with Embellishments",
        "description": "Stunning kaftan dress featuring hand-sewn beads and sequin embellishments. Flowing silhouette perfect for all body types. Breathable fabric ideal for Nigerian climate.",
        "category": "Women's Fashion",
        "base_price": 32000,
        "inventory_quantity": 40,
        "vendor_name": "Zainab's Couture",
        "images": [
            "https://images.unsplash.com/photo-1583391733956-6c78276477e2?w=800&h=800&fit=crop",
            "https://images.unsplash.com/photo-1591369822096-ffd140ec948f?w=800&h=800&fit=crop"
        ],
        "variants": [
            {"sku": "KFT-EMB-S-001", "option_name": "Size", "option_value": "Small", "price": 32000, "compare_at_price": 40000, "inventory_quantity": 10},
            {"sku": "KFT-EMB-M-001", "option_name": "Size", "option_value": "Medium", "price": 32000, "compare_at_price": 40000, "inventory_quantity": 15},
            {"sku": "KFT-EMB-L-001", "option_name": "Size", "option_value": "Large", "price": 33000, "compare_at_price": 41000, "inventory_quantity": 15}
        ]
    },
    {
        "title": "Men's Senator Wear Complete Set",
        "description": "Modern senator style outfit with contemporary cut. Includes matching top and trousers. Perfect blend of traditional and modern fashion. Comfortable and stylish.",
        "category": "Men's Fashion",
        "base_price": 28000,
        "inventory_quantity": 45,
        "vendor_name": "Royal Threads Nigeria",
        "images": [
            "https://images.unsplash.com/photo-1594938298603-c8148c4dae35?w=800&h=800&fit=crop",
            "https://images.unsplash.com/photo-1617127365659-c47fa864d8bc?w=800&h=800&fit=crop"
        ],
        "variants": [
            {"sku": "SEN-SET-M-001", "option_name": "Size", "option_value": "Medium", "price": 28000, "compare_at_price": 35000, "inventory_quantity": 15},
            {"sku": "SEN-SET-L-001", "option_name": "Size", "option_value": "Large", "price": 28000, "compare_at_price": 35000, "inventory_quantity": 18},
            {"sku": "SEN-SET-XL-001", "option_name": "Size", "option_value": "X-Large", "price": 29500, "compare_at_price": 36500, "inventory_quantity": 12}
        ]
    },
    {
        "title": "Aso Ebi Lace Fabric Set",
        "description": "Premium quality French lace fabric perfect for aso ebi. 5 yards of exquisite lace with intricate patterns. Ideal for creating stunning outfits for special occasions.",
        "category": "Women's Fashion",
        "base_price": 42000,
        "inventory_quantity": 25,
        "vendor_name": "Aso Oke Treasures",
        "images": [
            "https://images.unsplash.com/photo-1617922001439-4a2e6562f328?w=800&h=800&fit=crop",
            "https://images.unsplash.com/photo-1610652492500-ded49c1886c6?w=800&h=800&fit=crop"
        ],
        "variants": [
            {"sku": "LACE-5YD-NAVY", "option_name": "Color", "option_value": "Navy Blue", "price": 42000, "compare_at_price": 50000, "inventory_quantity": 8},
            {"sku": "LACE-5YD-WINE", "option_name": "Color", "option_value": "Wine", "price": 42000, "compare_at_price": 50000, "inventory_quantity": 9},
            {"sku": "LACE-5YD-PEACH", "option_name": "Color", "option_value": "Peach", "price": 43000, "compare_at_price": 51000, "inventory_quantity": 8}
        ]
    },
    {
        "title": "Buba and Sokoto Combo",
        "description": "Traditional Yoruba men's outfit with modern twist. Comfortable buba (top) with matching sokoto (trousers). High-quality fabric that maintains shape and color.",
        "category": "Men's Fashion",
        "base_price": 22000,
        "inventory_quantity": 60,
        "vendor_name": "Adaeze Collections",
        "images": [
            "https://images.unsplash.com/photo-1622470953794-aa9c70b0fb9d?w=800&h=800&fit=crop",
            "https://images.unsplash.com/photo-1594938298603-c8148c4dae35?w=800&h=800&fit=crop"
        ],
        "variants": [
            {"sku": "BUB-SOK-M-001", "option_name": "Size", "option_value": "Medium", "price": 22000, "compare_at_price": 28000, "inventory_quantity": 20},
            {"sku": "BUB-SOK-L-001", "option_name": "Size", "option_value": "Large", "price": 22000, "compare_at_price": 28000, "inventory_quantity": 25},
            {"sku": "BUB-SOK-XL-001", "option_name": "Size", "option_value": "X-Large", "price": 23000, "compare_at_price": 29000, "inventory_quantity": 15}
        ]
    },
    {
        "title": "Maxi Wrapper Skirt with Blouse",
        "description": "Elegant wrapper skirt set with fitted blouse. Features African print patterns and modern design. Perfect for office wear and social events. Comfortable all-day wear.",
        "category": "Women's Fashion",
        "base_price": 18500,
        "inventory_quantity": 55,
        "vendor_name": "Zainab's Couture",
        "images": [
            "https://images.unsplash.com/photo-1591369822096-ffd140ec948f?w=800&h=800&fit=crop",
            "https://images.unsplash.com/photo-1595777457583-95e059d581b8?w=800&h=800&fit=crop"
        ],
        "variants": [
            {"sku": "WRP-BLS-S-001", "option_name": "Size", "option_value": "Small", "price": 18500, "compare_at_price": 24000, "inventory_quantity": 18},
            {"sku": "WRP-BLS-M-001", "option_name": "Size", "option_value": "Medium", "price": 18500, "compare_at_price": 24000, "inventory_quantity": 20},
            {"sku": "WRP-BLS-L-001", "option_name": "Size", "option_value": "Large", "price": 19000, "compare_at_price": 24500, "inventory_quantity": 17}
        ]
    },
    {
        "title": "Native Cap (Fila) Collection",
        "description": "Handwoven traditional Yoruba cap (fila) in various styles. Authentic craftsmanship with modern appeal. Perfect accessory for traditional outfits. One size fits most.",
        "category": "Men's Fashion",
        "base_price": 5500,
        "inventory_quantity": 80,
        "vendor_name": "Royal Threads Nigeria",
        "images": [
            "https://images.unsplash.com/photo-1588850561407-ed78c282e89b?w=800&h=800&fit=crop",
            "https://images.unsplash.com/photo-1576871337632-b9aef4c17ab9?w=800&h=800&fit=crop"
        ],
        "variants": [
            {"sku": "FILA-001-BLACK", "option_name": "Color", "option_value": "Black", "price": 5500, "compare_at_price": 7500, "inventory_quantity": 25},
            {"sku": "FILA-001-BROWN", "option_name": "Color", "option_value": "Brown", "price": 5500, "compare_at_price": 7500, "inventory_quantity": 30},
            {"sku": "FILA-001-NAVY", "option_name": "Color", "option_value": "Navy", "price": 6000, "compare_at_price": 8000, "inventory_quantity": 25}
        ]
    },
    {
        "title": "Two-Piece Peplum Top and Skirt",
        "description": "Contemporary African fashion with peplum top and pencil skirt. Flattering silhouette with ankara print accents. Perfect for work and social events. Premium quality fabric.",
        "category": "Women's Fashion",
        "base_price": 27500,
        "inventory_quantity": 35,
        "vendor_name": "Adaeze Collections",
        "images": [
            "https://images.unsplash.com/photo-1596783074918-c84cb06531ca?w=800&h=800&fit=crop",
            "https://images.unsplash.com/photo-1583391733956-6c78276477e2?w=800&h=800&fit=crop"
        ],
        "variants": [
            {"sku": "PEP-SET-S-001", "option_name": "Size", "option_value": "Small", "price": 27500, "compare_at_price": 34000, "inventory_quantity": 10},
            {"sku": "PEP-SET-M-001", "option_name": "Size", "option_value": "Medium", "price": 27500, "compare_at_price": 34000, "inventory_quantity": 15},
            {"sku": "PEP-SET-L-001", "option_name": "Size", "option_value": "Large", "price": 28000, "compare_at_price": 34500, "inventory_quantity": 10}
        ]
    }
]


async def create_product(client: httpx.AsyncClient, product_data: Dict, token: str) -> Dict:
    """Create a product with images and variants"""

    size_guide = build_size_guide(product_data)
    product_variants = build_variants(product_data)
    total_stock = len(product_variants) * 40

    image_entries = [
        {
            "image_url": url,
            "thumbnail_url": url,
            "alt_text": f"{product_data['title']} - Image {idx + 1}",
            "display_order": idx,
            "is_primary": idx == 0,
        }
        for idx, url in enumerate(product_data["images"])
    ]

    product_payload = {
        "title": product_data["title"],
        "description": product_data["description"],
        "base_price": product_data["base_price"],
        "compare_at_price": float(Decimal(str(product_data["base_price"])) * Decimal("1.15")),
        "total_stock": total_stock,
        "status": "active",
        "is_featured": True,
        "size_guide": size_guide,
        "variants": product_variants,
        "images": image_entries,
    }

    # Create product
    response = await client.post(
        f"{BASE_URL}/products",
        json=product_payload,
        headers={"Authorization": f"Bearer {token}"},
        follow_redirects=True
    )

    if response.status_code != 201:
        print(f"Failed to create product: {product_data['title']}")
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
        return None

    product = response.json()
    product_id = product["id"]
    print(f"✓ Created product: {product_data['title']} (ID: {product_id})")

    return product


async def get_or_create_vendor_token(client: httpx.AsyncClient, vendor_name: str) -> str:
    """Get authentication token for a vendor (create vendor if needed)"""

    # Generate unique email for each vendor (add timestamp to make it unique)
    import time
    clean_name = vendor_name.lower().replace(' ', '').replace("'", '')
    timestamp = int(time.time() * 1000) % 100000  # Use last 5 digits of timestamp
    email = f"{clean_name}{timestamp}@shopsoma.com"
    password = "VendorPass123!"

    register_payload = {
        "email": email,
        "password": password,
        "full_name": vendor_name,
        "phone_number": f"+234{80 + hash(vendor_name) % 20}{hash(vendor_name) % 10000000:07d}",
        "role": "vendor"
    }

    # Try to register (will fail if already exists, which is fine)
    reg_response = await client.post(f"{BASE_URL}/auth/signup", json=register_payload)
    if reg_response.status_code == 201:
        print(f"✓ Created new vendor: {vendor_name}")
    elif reg_response.status_code != 400:  # Not "already exists" error
        print(f"⚠ Vendor registration returned {reg_response.status_code}: {reg_response.text}")

    # Login to get token
    login_payload = {
        "email": email,
        "password": password
    }

    response = await client.post(
        f"{BASE_URL}/auth/login",
        json=login_payload
    )

    if response.status_code == 200:
        token_data = response.json()
        print(f"✓ Logged in as vendor: {vendor_name}")
        return token_data["access_token"]
    else:
        print(f"✗ Failed to login as {vendor_name}: {response.text}")
        return None


async def seed_products():
    """Main function to seed all products"""
    async with httpx.AsyncClient(timeout=30.0) as client:
        print("\n" + "="*60)
        print("SHOPSOMA DEMO PRODUCT SEEDER")
        print("="*60 + "\n")

        # Group products by vendor
        vendor_products = {}
        for product in DEMO_PRODUCTS:
            vendor = product["vendor_name"]
            if vendor not in vendor_products:
                vendor_products[vendor] = []
            vendor_products[vendor].append(product)

        # Create products for each vendor
        for vendor_name, products in vendor_products.items():
            print(f"\n{'='*60}")
            print(f"Processing vendor: {vendor_name}")
            print(f"{'='*60}\n")

            # Get vendor token
            token = await get_or_create_vendor_token(client, vendor_name)
            if not token:
                print(f"Skipping vendor {vendor_name} - authentication failed\n")
                continue

            # Create products
            for product_data in products:
                await create_product(client, product_data, token)
                print()  # Add spacing

        print("\n" + "="*60)
        print("SEEDING COMPLETE!")
        print("="*60 + "\n")
        print(f"Total products created: {len(DEMO_PRODUCTS)}")
        print(f"Total vendors: {len(vendor_products)}")
        print("\nYou can now view these products in your frontend!\n")


if __name__ == "__main__":
    asyncio.run(seed_products())
