"""
Seed 40 high-quality demo products across Men, Women, Beauty, Perfumes,
Accessories, and Shop Edits for local development.

SAFETY REQUIREMENT:
This script contains an explicit guard that strictly verifies the host is localhost
and ENVIRONMENT is development/local, refusing to execute on staging or production.
"""

import asyncio
import sys
import uuid
import urllib.parse
from decimal import Decimal
from typing import Dict, List, Any

# Ensure UTF-8 output on Windows terminal
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.security import get_password_hash
from app.models.category import Category
from app.models.user import User, UserRole
from app.models.vendor import Vendor, KYCStatus
from app.models.stock_payment_persistence import coordinate_catalog_write
from app.models.product import (
    Product,
    ProductVariant,
    ProductImage,
    ProductStatus,
    ModerationStatus,
    ProductType,
    Variation,
    SizeStock,
    SizeEnum,
)


def verify_local_environment():
    """Ensure this script runs ONLY on a local development host."""
    env = (settings.ENVIRONMENT or "").lower()
    if env not in ("development", "local", "dev", "test"):
        raise RuntimeError(
            f"REFUSING TO RUN: settings.ENVIRONMENT is '{settings.ENVIRONMENT}'. "
            f"This seed script is strictly restricted to local host development!"
        )

    parsed_db = urllib.parse.urlparse(str(settings.DATABASE_URL))
    db_host = (parsed_db.hostname or "").lower()
    allowed_local_hosts = ("localhost", "127.0.0.1", "::1", "host.docker.internal", "testserver")

    if db_host not in allowed_local_hosts:
        raise RuntimeError(
            f"REFUSING TO RUN: DATABASE_URL points to host '{db_host}', which is not local! "
            f"This script MUST NEVER be run against remote or cloud databases."
        )

    print(f"[SAFEGUARD PASSED] Local host verified: Host='{db_host}', Env='{env}'\n")


# Sizing guides for realistic African and contemporary fashion
SIZE_GUIDES = {
    "men_clothing": {
        "title": "Men's Size Guide",
        "subtitle": "Contemporary & Traditional Menswear",
        "gender": "Men",
        "rows": [
            {"label": "S", "standard": "EU 48 / US 38", "measurement": 'Chest 38" / Waist 32"'},
            {"label": "M", "standard": "EU 50 / US 40", "measurement": 'Chest 40" / Waist 34"'},
            {"label": "L", "standard": "EU 52 / US 42", "measurement": 'Chest 42" / Waist 36"'},
            {"label": "XL", "standard": "EU 54 / US 44", "measurement": 'Chest 44" / Waist 38"'},
            {"label": "XXL", "standard": "EU 56 / US 46", "measurement": 'Chest 46" / Waist 40"'},
        ],
    },
    "women_clothing": {
        "title": "Women's Size Guide",
        "subtitle": "Signature Silhouettes & Contemporary Fit",
        "gender": "Women",
        "rows": [
            {"label": "XS", "standard": "UK 6 / US 2", "measurement": 'Bust 32" / Waist 24" / Hips 35"'},
            {"label": "S", "standard": "UK 8 / US 4", "measurement": 'Bust 34" / Waist 26" / Hips 37"'},
            {"label": "M", "standard": "UK 10 / US 6", "measurement": 'Bust 36" / Waist 28" / Hips 39"'},
            {"label": "L", "standard": "UK 12 / US 8", "measurement": 'Bust 38" / Waist 30" / Hips 41"'},
            {"label": "XL", "standard": "UK 14 / US 10", "measurement": 'Bust 40" / Waist 32" / Hips 43"'},
        ],
    },
    "footwear": {
        "title": "Footwear Size Guide",
        "subtitle": "European Standard Sizing",
        "gender": "Unisex",
        "rows": [
            {"label": "40", "standard": "UK 6.5 / US 7.5", "measurement": "Foot length 25.4 cm"},
            {"label": "41", "standard": "UK 7 / US 8", "measurement": "Foot length 26.0 cm"},
            {"label": "42", "standard": "UK 8 / US 9", "measurement": "Foot length 26.7 cm"},
            {"label": "43", "standard": "UK 9 / US 10", "measurement": "Foot length 27.3 cm"},
            {"label": "44", "standard": "UK 9.5 / US 10.5", "measurement": "Foot length 28.0 cm"},
            {"label": "45", "standard": "UK 10.5 / US 11.5", "measurement": "Foot length 28.7 cm"},
        ],
    },
    "accessories": {
        "title": "Accessories Size Guide",
        "subtitle": "Standard Sizing",
        "gender": "Unisex",
        "rows": [
            {"label": "One Size", "standard": "Universal Fit", "measurement": "Adjustable / Standard Proportion"},
        ],
    },
}

SIZE_ENUM_MAP = {
    "XXS": SizeEnum.XXS,
    "XS": SizeEnum.XS,
    "S": SizeEnum.S,
    "M": SizeEnum.M,
    "L": SizeEnum.L,
    "XL": SizeEnum.XL,
    "XXL": SizeEnum.XXL,
    "XXXL": SizeEnum.XXXL,
    "One Size": SizeEnum.ONE_SIZE,
    "One/Size": SizeEnum.ONE_SIZE,
}

VENDORS_SEED = [
    {
        "email": "vendor@shopsoma.com",
        "name": "Shopsoma Fashion Studio",
        "business_name": "Shopsoma Studio",
        "business_description": "Curated African luxury, clean silhouettes, and contemporary craftsmanship.",
        "is_featured_storefront": True,
    },
    {
        "email": "adaeze@shopsoma.com",
        "name": "Adaeze Nwosu",
        "business_name": "Adaeze Collections",
        "business_description": "Contemporary African womenswear, bold statement tailoring, and artisanal dresses.",
        "is_featured_storefront": True,
    },
    {
        "email": "royalthreads@shopsoma.com",
        "name": "Olumide Adeleke",
        "business_name": "Royal Threads Nigeria",
        "business_description": "Heritage Nigerian menswear, handcrafted Agbada, Senator sets, and fine leatherwork.",
        "is_featured_storefront": True,
    },
]

PRODUCTS_SEED_DATA = [
    # ==========================================
    # MEN'S FASHION
    # ==========================================
    {
        "title": "Adire Silk Resort Shirt",
        "description": "Luxurious camp-collar shirt hand-dyed using traditional Adire resistance techniques on pure silk twill. Features natural mother-of-pearl buttons and a relaxed silhouette crafted for warm days and evening gatherings.",
        "category_slug": "men-tops-shirts",
        "vendor_business": "Royal Threads Nigeria",
        "base_price": Decimal("28000.00"),
        "compare_at_price": Decimal("34000.00"),
        "is_featured": True,
        "size_guide_type": "men_clothing",
        "shop_edit_slugs": ["shop-edits-occasion-wear-casual", "shop-edits-occasion-wear-party"],
        "colors": [
            {"name": "Indigo Blue", "hex": "#1B3B6F"},
            {"name": "Sahara Ochre", "hex": "#C68E17"},
        ],
        "sizes": ["S", "M", "L", "XL", "XXL"],
        "images": [
            "https://images.unsplash.com/photo-1602810318383-e386cc2a3ccf?w=1000&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1596755094514-f87e34085b2c?w=1000&auto=format&fit=crop",
        ],
    },
    {
        "title": "Embroidered Grandad Collar Linen Shirt",
        "description": "Crisp European linen shirt with minimalist tone-on-tone embroidery along the hidden placket and mandarin collar. Breathable, structured, and effortlessly refined.",
        "category_slug": "men-tops-shirts",
        "vendor_business": "Shopsoma Studio",
        "base_price": Decimal("24500.00"),
        "compare_at_price": Decimal("30000.00"),
        "is_featured": False,
        "size_guide_type": "men_clothing",
        "shop_edit_slugs": ["shop-edits-occasion-wear-casual", "shop-edits-occasion-wear-workwear"],
        "colors": [
            {"name": "Pure White", "hex": "#FFFFFF"},
            {"name": "Desert Sand", "hex": "#D2B48C"},
            {"name": "Olive Green", "hex": "#556B2F"},
        ],
        "sizes": ["S", "M", "L", "XL", "XXL"],
        "images": [
            "https://images.unsplash.com/photo-1618354691373-d851c5c3a990?w=1000&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1620799140408-edc6dcb6d633?w=1000&auto=format&fit=crop",
        ],
    },
    {
        "title": "Ankara Pocket Heavyweight Cotton T-Shirt",
        "description": "Heavyweight 240gsm organic combed cotton t-shirt with an authentic wax print chest pocket detail. Ribbed crew collar with a durable double-stitched hem.",
        "category_slug": "men-tops-t-shirts",
        "vendor_business": "Shopsoma Studio",
        "base_price": Decimal("14000.00"),
        "compare_at_price": Decimal("18000.00"),
        "is_featured": False,
        "size_guide_type": "men_clothing",
        "shop_edit_slugs": ["shop-edits-occasion-wear-casual"],
        "colors": [
            {"name": "Onyx Black", "hex": "#111827"},
            {"name": "Heather Grey", "hex": "#9CA3AF"},
            {"name": "Chalk White", "hex": "#F9FAFB"},
        ],
        "sizes": ["S", "M", "L", "XL", "XXL"],
        "images": [
            "https://images.unsplash.com/photo-1521572267360-ee0c2909d518?w=1000&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1583743814966-8936f5b7be1a?w=1000&auto=format&fit=crop",
        ],
    },
    {
        "title": "Heritage Indigo Graphic Boxy Tee",
        "description": "Drop-shoulder boxy silhouette featuring screen-printed geometric tribal typography inspired by West African folklore. Pre-shrunk for lasting structure.",
        "category_slug": "men-tops-t-shirts",
        "vendor_business": "Royal Threads Nigeria",
        "base_price": Decimal("16500.00"),
        "compare_at_price": Decimal("20000.00"),
        "is_featured": False,
        "size_guide_type": "men_clothing",
        "shop_edit_slugs": ["shop-edits-occasion-wear-casual"],
        "colors": [
            {"name": "Washed Indigo", "hex": "#264653"},
            {"name": "Charcoal", "hex": "#36454F"},
        ],
        "sizes": ["S", "M", "L", "XL", "XXL"],
        "images": [
            "https://images.unsplash.com/photo-1576566588028-4147f3842f27?w=1000&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1503342217505-b0a15ec3261c?w=1000&auto=format&fit=crop",
        ],
    },
    {
        "title": "Modern Royal Agbada 3-Piece Set",
        "description": "Statement 3-piece Agbada ensemble crafted from heavy raw silk damask with hand-guided metallic thread embroidery along the chest and back. Includes flowing robe, tailored caftan inner, and drawstring trousers.",
        "category_slug": "men-sets-trouser-sets",
        "vendor_business": "Royal Threads Nigeria",
        "base_price": Decimal("85000.00"),
        "compare_at_price": Decimal("110000.00"),
        "is_featured": True,
        "size_guide_type": "men_clothing",
        "shop_edit_slugs": ["shop-edits-occasion-wear-evening", "shop-edits-occasion-wear-party"],
        "colors": [
            {"name": "Emerald Green", "hex": "#0F766E"},
            {"name": "Regal White", "hex": "#FAFAFA"},
            {"name": "Midnight Navy", "hex": "#0A192F"},
        ],
        "sizes": ["M", "L", "XL", "XXL"],
        "images": [
            "https://images.unsplash.com/photo-1617127365659-c47fa864d8bc?w=1000&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1594938298603-c8148c4dae35?w=1000&auto=format&fit=crop",
        ],
    },
    {
        "title": "Contemporary Senator Suit with Geometric Trim",
        "description": "Tailored two-piece Senator wear in premium stretch cashmere-wool blend. Features contrast geometric welt details along the asymmetric chest closure.",
        "category_slug": "men-sets-trouser-sets",
        "vendor_business": "Royal Threads Nigeria",
        "base_price": Decimal("58000.00"),
        "compare_at_price": Decimal("72000.00"),
        "is_featured": True,
        "size_guide_type": "men_clothing",
        "shop_edit_slugs": ["shop-edits-occasion-wear-workwear", "shop-edits-occasion-wear-evening"],
        "colors": [
            {"name": "Charcoal Slate", "hex": "#2F3E46"},
            {"name": "Burgundy", "hex": "#800020"},
            {"name": "Deep Navy", "hex": "#000080"},
        ],
        "sizes": ["S", "M", "L", "XL", "XXL"],
        "images": [
            "https://images.unsplash.com/photo-1507679799987-c73779587ccf?w=1000&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1593030761757-71fae45fa0e7?w=1000&auto=format&fit=crop",
        ],
    },
    {
        "title": "Linen Safari Camp Collar Short Set",
        "description": "Two-piece resort coordinate set featuring a camp collar utility shirt with four patch pockets and matching pleated drawstring shorts in pure washed linen.",
        "category_slug": "men-sets-shorts-sets",
        "vendor_business": "Shopsoma Studio",
        "base_price": Decimal("38000.00"),
        "compare_at_price": Decimal("46000.00"),
        "is_featured": False,
        "size_guide_type": "men_clothing",
        "shop_edit_slugs": ["shop-edits-occasion-wear-casual"],
        "colors": [
            {"name": "Terracotta", "hex": "#E2725B"},
            {"name": "Sage Green", "hex": "#9DC183"},
            {"name": "Natural Ecru", "hex": "#F5F5DC"},
        ],
        "sizes": ["S", "M", "L", "XL"],
        "images": [
            "https://images.unsplash.com/photo-1506152983158-b4a74a01c721?w=1000&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1591195853828-11db59a44f6b?w=1000&auto=format&fit=crop",
        ],
    },
    {
        "title": "Pleated Tapered Wool Trousers",
        "description": "Double-pleated tailored trousers cut from tropical virgin wool. Features adjustable side waist tabs, concealed horn button fly, and clean turned-up cuffs.",
        "category_slug": "men-bottoms-trousers",
        "vendor_business": "Royal Threads Nigeria",
        "base_price": Decimal("32000.00"),
        "compare_at_price": Decimal("39000.00"),
        "is_featured": False,
        "size_guide_type": "men_clothing",
        "shop_edit_slugs": ["shop-edits-occasion-wear-workwear", "shop-edits-occasion-wear-evening"],
        "colors": [
            {"name": "Camel Brown", "hex": "#C19A6B"},
            {"name": "Charcoal", "hex": "#36454F"},
            {"name": "Onyx Black", "hex": "#111827"},
        ],
        "sizes": ["S", "M", "L", "XL"],
        "images": [
            "https://images.unsplash.com/photo-1473966968600-fa801b869a1a?w=1000&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1624378439575-d8705ad7ae80?w=1000&auto=format&fit=crop",
        ],
    },
    {
        "title": "Selvedge Raw Indigo Denim Jeans",
        "description": "14oz Japanese shuttle-loom selvedge denim in a contemporary straight-taper fit. Classic copper rivets, button fly, and natural indigo dyed yarn designed to fade beautifully.",
        "category_slug": "men-bottoms-jeans",
        "vendor_business": "Shopsoma Studio",
        "base_price": Decimal("29500.00"),
        "compare_at_price": Decimal("36000.00"),
        "is_featured": False,
        "size_guide_type": "men_clothing",
        "shop_edit_slugs": ["shop-edits-occasion-wear-casual"],
        "colors": [
            {"name": "Dark Raw Indigo", "hex": "#1A2A3A"},
            {"name": "Black Overdye", "hex": "#181818"},
        ],
        "sizes": ["S", "M", "L", "XL"],
        "images": [
            "https://images.unsplash.com/photo-1542272604-787c3835535d?w=1000&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1541099649105-f69ad21f3246?w=1000&auto=format&fit=crop",
        ],
    },
    {
        "title": "Tailored Linen Drawstring Bermuda Shorts",
        "description": "Relaxed knee-length Bermuda shorts crafted in high-density Irish linen with an elasticated waistband and natural cotton braided cord.",
        "category_slug": "men-bottoms-shorts",
        "vendor_business": "Shopsoma Studio",
        "base_price": Decimal("18500.00"),
        "compare_at_price": Decimal("23000.00"),
        "is_featured": False,
        "size_guide_type": "men_clothing",
        "shop_edit_slugs": ["shop-edits-occasion-wear-casual"],
        "colors": [
            {"name": "Stone Beige", "hex": "#D1C7BD"},
            {"name": "Navy Blue", "hex": "#000080"},
            {"name": "Olive Green", "hex": "#556B2F"},
        ],
        "sizes": ["S", "M", "L", "XL"],
        "images": [
            "https://images.unsplash.com/photo-1591195853828-11db59a44f6b?w=1000&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1506152983158-b4a74a01c721?w=1000&auto=format&fit=crop",
        ],
    },
    {
        "title": "Wax Print Reversible Bomber Jacket",
        "description": "Reversible outerwear featuring structured African wax print cotton on one side and water-repellent matte nylon on the other. Heavyweight brass front zip and rib-knit cuffs.",
        "category_slug": "men-outerwear-jackets",
        "vendor_business": "Royal Threads Nigeria",
        "base_price": Decimal("42000.00"),
        "compare_at_price": Decimal("52000.00"),
        "is_featured": False,
        "size_guide_type": "men_clothing",
        "shop_edit_slugs": ["shop-edits-occasion-wear-casual", "shop-edits-occasion-wear-party"],
        "colors": [
            {"name": "Gold/Black Print", "hex": "#D4AF37"},
            {"name": "Teal/Orange Print", "hex": "#008080"},
        ],
        "sizes": ["M", "L", "XL", "XXL"],
        "images": [
            "https://images.unsplash.com/photo-1551028719-00167b16eac5?w=1000&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1548883354-7622d03aca27?w=1000&auto=format&fit=crop",
        ],
    },
    {
        "title": "Heavyweight French Terry Streetwear Hoodie",
        "description": "480gsm custom-milled French terry cotton hoodie with double-layer hood, hidden phone stash pocket in kangaroo pouch, and subtle tonal embroidery.",
        "category_slug": "men-outerwear-hoodies",
        "vendor_business": "Shopsoma Studio",
        "base_price": Decimal("22000.00"),
        "compare_at_price": Decimal("28000.00"),
        "is_featured": False,
        "size_guide_type": "men_clothing",
        "shop_edit_slugs": ["shop-edits-occasion-wear-casual"],
        "colors": [
            {"name": "Forest Green", "hex": "#1E3F20"},
            {"name": "Vintage Black", "hex": "#222222"},
            {"name": "Heather Grey", "hex": "#A0A0A0"},
        ],
        "sizes": ["S", "M", "L", "XL", "XXL"],
        "images": [
            "https://images.unsplash.com/photo-1556821840-3a63f95609a7?w=1000&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1578587018452-892bacefd3f2?w=1000&auto=format&fit=crop",
        ],
    },
    {
        "title": "Handcrafted Calfskin Leather Chelsea Boots",
        "description": "Artisan Goodyear-welted Chelsea boots built from supple Italian calfskin leather with durable Dainite rubber studded soles and elasticated side gores.",
        "category_slug": "men-shoes-formal",
        "vendor_business": "Royal Threads Nigeria",
        "base_price": Decimal("48000.00"),
        "compare_at_price": Decimal("60000.00"),
        "is_featured": True,
        "size_guide_type": "footwear",
        "shop_edit_slugs": ["shop-edits-occasion-wear-evening", "shop-edits-occasion-wear-workwear"],
        "colors": [
            {"name": "Espresso Brown", "hex": "#3D2314"},
            {"name": "Onyx Black", "hex": "#111827"},
        ],
        "sizes": ["41", "42", "43", "44", "45"],
        "images": [
            "https://images.unsplash.com/photo-1638247025967-b4e38f787b76?w=1000&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1549298916-b41d501d3772?w=1000&auto=format&fit=crop",
        ],
    },
    {
        "title": "Minimalist Low-Top Nappa Leather Sneakers",
        "description": "Full-grain buttery Nappa leather cupsole sneakers with stitched margom rubber outsoles and memory-foam leather insoles.",
        "category_slug": "men-shoes-casual",
        "vendor_business": "Shopsoma Studio",
        "base_price": Decimal("36000.00"),
        "compare_at_price": Decimal("45000.00"),
        "is_featured": False,
        "size_guide_type": "footwear",
        "shop_edit_slugs": ["shop-edits-occasion-wear-casual"],
        "colors": [
            {"name": "Pure White", "hex": "#FFFFFF"},
            {"name": "Triple Black", "hex": "#000000"},
        ],
        "sizes": ["41", "42", "43", "44", "45"],
        "images": [
            "https://images.unsplash.com/photo-1525966222134-fcfa99b8ae77?w=1000&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1606107557195-0e29a4b5b4aa?w=1000&auto=format&fit=crop",
        ],
    },
    {
        "title": "Hand-Embroidered Velvet Fila Cap",
        "description": "Traditional Yoruba ceremonial Fila cap hand-stitched in rich cotton velvet with metallic silver threading. Foldable to the wearer's preferred tilt.",
        "category_slug": "men-accessories-caps-hats",
        "vendor_business": "Royal Threads Nigeria",
        "base_price": Decimal("12500.00"),
        "compare_at_price": Decimal("16000.00"),
        "is_featured": False,
        "size_guide_type": "accessories",
        "shop_edit_slugs": ["shop-edits-occasion-wear-party", "shop-edits-occasion-wear-evening"],
        "colors": [
            {"name": "Royal Burgundy", "hex": "#800020"},
            {"name": "Midnight Navy", "hex": "#000080"},
            {"name": "Forest Green", "hex": "#0B6623"},
        ],
        "sizes": ["One Size"],
        "images": [
            "https://images.unsplash.com/photo-1521572163474-6864f9cf17ab?w=1000&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1529958030586-3aae4ca485ff?w=1000&auto=format&fit=crop",
        ],
    },
    {
        "title": "Braided Italian Bridle Leather Belt",
        "description": "Individually hand-braided vegetable-tanned bridle leather belt with solid brushed brass buckle. Pairs effortlessly with chinos, denim, or tailored suits.",
        "category_slug": "men-accessories-belts",
        "vendor_business": "Shopsoma Studio",
        "base_price": Decimal("15000.00"),
        "compare_at_price": Decimal("19000.00"),
        "is_featured": False,
        "size_guide_type": "accessories",
        "shop_edit_slugs": ["shop-edits-occasion-wear-workwear"],
        "colors": [
            {"name": "Cognac Brown", "hex": "#9A3821"},
            {"name": "Pitch Black", "hex": "#000000"},
        ],
        "sizes": ["S", "M", "L", "XL"],
        "images": [
            "https://images.unsplash.com/photo-1624222247344-550fb60583dc?w=1000&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1553062407-98eeb64c6a62?w=1000&auto=format&fit=crop",
        ],
    },
    {
        "title": "Full-Grain Leather Bifold Cardholder Wallet",
        "description": "Ultra-slim front pocket wallet hand-burnished from full-grain vegetable tanned leather with 6 card slots and a central banknote divider.",
        "category_slug": "men-accessories-wallets",
        "vendor_business": "Shopsoma Studio",
        "base_price": Decimal("16000.00"),
        "compare_at_price": Decimal("21000.00"),
        "is_featured": False,
        "size_guide_type": "accessories",
        "shop_edit_slugs": ["shop-edits-occasion-wear-workwear", "shop-edits-occasion-wear-casual"],
        "colors": [
            {"name": "Tan", "hex": "#D2B48C"},
            {"name": "Jet Black", "hex": "#111111"},
        ],
        "sizes": ["One Size"],
        "images": [
            "https://images.unsplash.com/photo-1627123424574-724758594e93?w=1000&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1517256064527-09c73fc73e38?w=1000&auto=format&fit=crop",
        ],
    },
    {
        "title": "Tortoiseshell Acetate Aviator Sunglasses",
        "description": "Hand-polished Mazzucchelli Italian acetate sunglasses with 100% UVA/UVB polarized lenses and five-barrel German engineered hinges.",
        "category_slug": "men-accessories-sunglasses",
        "vendor_business": "Shopsoma Studio",
        "base_price": Decimal("22500.00"),
        "compare_at_price": Decimal("28000.00"),
        "is_featured": False,
        "size_guide_type": "accessories",
        "shop_edit_slugs": ["shop-edits-occasion-wear-casual", "shop-edits-occasion-wear-party"],
        "colors": [
            {"name": "Amber Tortoise", "hex": "#B87333"},
            {"name": "Polished Black", "hex": "#1A1A1A"},
        ],
        "sizes": ["One Size"],
        "images": [
            "https://images.unsplash.com/photo-1511499767150-a48a237f0083?w=1000&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1508296695146-257a814070b4?w=1000&auto=format&fit=crop",
        ],
    },

    # ==========================================
    # WOMEN'S FASHION
    # ==========================================
    {
        "title": "Artisan Tiered Linen Wrap Midi Dress",
        "description": "Handmade wrap midi dress in pre-washed 100% Belgian flax linen. Features delicate tiered ruffles, an adjustable tie waist, and concealed side seam pockets.",
        "category_slug": "women-dresses-casual",
        "vendor_business": "Adaeze Collections",
        "base_price": Decimal("34000.00"),
        "compare_at_price": Decimal("42000.00"),
        "is_featured": True,
        "size_guide_type": "women_clothing",
        "shop_edit_slugs": ["shop-edits-occasion-wear-casual"],
        "colors": [
            {"name": "Terracotta Rust", "hex": "#C85A32"},
            {"name": "Sage Herb", "hex": "#9DC183"},
            {"name": "Butter Cream", "hex": "#FFFDD0"},
        ],
        "sizes": ["XS", "S", "M", "L", "XL"],
        "images": [
            "https://images.unsplash.com/photo-1515372039744-b8f02a3ae446?w=1000&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1496747611176-843222e1e57c?w=1000&auto=format&fit=crop",
        ],
    },
    {
        "title": "Corseted Metallic Jacquard Cocktail Dress",
        "description": "Showstopping cocktail dress in custom woven metallic lurex brocade with an internal boned corset bodice and an architectural asymmetric peplum hem.",
        "category_slug": "women-dresses-party",
        "vendor_business": "Adaeze Collections",
        "base_price": Decimal("46000.00"),
        "compare_at_price": Decimal("58000.00"),
        "is_featured": True,
        "size_guide_type": "women_clothing",
        "shop_edit_slugs": ["shop-edits-occasion-wear-party", "shop-edits-occasion-wear-evening"],
        "colors": [
            {"name": "Burnished Gold", "hex": "#D4AF37"},
            {"name": "Emerald Lustre", "hex": "#0F766E"},
            {"name": "Ruby Red", "hex": "#9B111E"},
        ],
        "sizes": ["XS", "S", "M", "L", "XL"],
        "images": [
            "https://images.unsplash.com/photo-1572804013309-59a88b7e92f1?w=1000&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1515886657613-9f3515b0c78f?w=1000&auto=format&fit=crop",
        ],
    },
    {
        "title": "Silk Charmeuse Draped Evening Gown",
        "description": "Fluid floor-length gown cut on the bias from 22-momme pure mulberry silk charmeuse. Accented by a sultry cowl neckline and elegant low back.",
        "category_slug": "women-dresses-formal",
        "vendor_business": "Adaeze Collections",
        "base_price": Decimal("62000.00"),
        "compare_at_price": Decimal("78000.00"),
        "is_featured": True,
        "size_guide_type": "women_clothing",
        "shop_edit_slugs": ["shop-edits-occasion-wear-evening", "shop-edits-occasion-wear-party"],
        "colors": [
            {"name": "Midnight Black", "hex": "#0B0B0B"},
            {"name": "Royal Sapphire", "hex": "#0F52BA"},
            {"name": "Champagne", "hex": "#F7E7CE"},
        ],
        "sizes": ["XS", "S", "M", "L", "XL"],
        "images": [
            "https://images.unsplash.com/photo-1566174053879-31528523f8ae?w=1000&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1518611012118-696072aa579a?w=1000&auto=format&fit=crop",
        ],
    },
    {
        "title": "Breezy Cotton Voile Resort Sun Dress",
        "description": "Light-as-air cotton voile tiered sundress with smocked back bodice and delicate self-tie shoulder straps. Perfect for tropical vacations and weekend brunches.",
        "category_slug": "women-dresses-beach-dresses",
        "vendor_business": "Adaeze Collections",
        "base_price": Decimal("27000.00"),
        "compare_at_price": Decimal("34000.00"),
        "is_featured": False,
        "size_guide_type": "women_clothing",
        "shop_edit_slugs": ["shop-edits-occasion-wear-casual"],
        "colors": [
            {"name": "Sunset Coral", "hex": "#FF6F61"},
            {"name": "Ocean Teal", "hex": "#008080"},
            {"name": "Coconut White", "hex": "#FAF9F6"},
        ],
        "sizes": ["S", "M", "L", "XL"],
        "images": [
            "https://images.unsplash.com/photo-1502716119720-b23a93e5fe1b?w=1000&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1595777457583-95e059d581b8?w=1000&auto=format&fit=crop",
        ],
    },
    {
        "title": "Silk Organza Sculptural Puff-Sleeve Blouse",
        "description": "Dramatic voluminous puff sleeves on a tailored silk organza bodice with covered silk button cuffs. Designed to make a refined entrance at formal lunches or dinners.",
        "category_slug": "women-tops-blouses",
        "vendor_business": "Adaeze Collections",
        "base_price": Decimal("28500.00"),
        "compare_at_price": Decimal("35000.00"),
        "is_featured": False,
        "size_guide_type": "women_clothing",
        "shop_edit_slugs": ["shop-edits-occasion-wear-evening", "shop-edits-occasion-wear-workwear"],
        "colors": [
            {"name": "Pearl Ivory", "hex": "#FDFBF7"},
            {"name": "Onyx Black", "hex": "#111827"},
            {"name": "Fuchsia Bloom", "hex": "#C154C1"},
        ],
        "sizes": ["XS", "S", "M", "L", "XL"],
        "images": [
            "https://images.unsplash.com/photo-1534126511673-b6899657816a?w=1000&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1589810635657-232948472d98?w=1000&auto=format&fit=crop",
        ],
    },
    {
        "title": "Oversized Crisp Poplin Boyfriend Shirt",
        "description": "Tailored in smooth 100% long-staple cotton poplin with a relaxed drop shoulder, elongated cuffs, and curved shirttail hem.",
        "category_slug": "women-tops-shirts",
        "vendor_business": "Shopsoma Studio",
        "base_price": Decimal("21000.00"),
        "compare_at_price": Decimal("26000.00"),
        "is_featured": False,
        "size_guide_type": "women_clothing",
        "shop_edit_slugs": ["shop-edits-occasion-wear-workwear", "shop-edits-occasion-wear-casual"],
        "colors": [
            {"name": "Optical White", "hex": "#FFFFFF"},
            {"name": "Sky Blue Stripe", "hex": "#87CEEB"},
        ],
        "sizes": ["XS", "S", "M", "L", "XL"],
        "images": [
            "https://images.unsplash.com/photo-1503342217505-b0a15ec3261c?w=1000&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1521572267360-ee0c2909d518?w=1000&auto=format&fit=crop",
        ],
    },
    {
        "title": "High-Waisted Flared Ankara Maxi Skirt",
        "description": "Sweeping full circle maxi skirt tailored from premium African wax print cotton with deep hidden pockets and a comfortable structured waistband.",
        "category_slug": "women-bottoms-skirts",
        "vendor_business": "Adaeze Collections",
        "base_price": Decimal("26000.00"),
        "compare_at_price": Decimal("33000.00"),
        "is_featured": False,
        "size_guide_type": "women_clothing",
        "shop_edit_slugs": ["shop-edits-occasion-wear-party", "shop-edits-occasion-wear-casual"],
        "colors": [
            {"name": "Multicolour Kente", "hex": "#E3A857"},
            {"name": "Peacock Blue Print", "hex": "#005F73"},
        ],
        "sizes": ["XS", "S", "M", "L", "XL"],
        "images": [
            "https://images.unsplash.com/photo-1583496661160-fb5886a0aaaa?w=1000&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1515886657613-9f3515b0c78f?w=1000&auto=format&fit=crop",
        ],
    },
    {
        "title": "Tailored High-Rise Crepe Palazzo Trousers",
        "description": "Floor-skimming wide-leg palazzo trousers tailored in Japanese heavy crepe with front knife pleats and clean waistband.",
        "category_slug": "women-bottoms-trousers",
        "vendor_business": "Shopsoma Studio",
        "base_price": Decimal("29000.00"),
        "compare_at_price": Decimal("36000.00"),
        "is_featured": False,
        "size_guide_type": "women_clothing",
        "shop_edit_slugs": ["shop-edits-occasion-wear-workwear", "shop-edits-occasion-wear-evening"],
        "colors": [
            {"name": "Vanilla Cream", "hex": "#F3E5AB"},
            {"name": "Classic Black", "hex": "#0A0A0A"},
            {"name": "Cocoa Brown", "hex": "#4E3629"},
        ],
        "sizes": ["XS", "S", "M", "L", "XL"],
        "images": [
            "https://images.unsplash.com/photo-1509631179647-0177331693ae?w=1000&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1473966968600-fa801b869a1a?w=1000&auto=format&fit=crop",
        ],
    },
    {
        "title": "Monochrome Linen Blazer & Wide Trouser Co-ord",
        "description": "Contemporary power suit tailored in 100% natural linen. Unlined relaxed double-breasted blazer paired with high-waisted pleated wide trousers.",
        "category_slug": "women-sets-trouser-sets",
        "vendor_business": "Adaeze Collections",
        "base_price": Decimal("54000.00"),
        "compare_at_price": Decimal("68000.00"),
        "is_featured": True,
        "size_guide_type": "women_clothing",
        "shop_edit_slugs": ["shop-edits-occasion-wear-workwear", "shop-edits-occasion-wear-casual"],
        "colors": [
            {"name": "Natural Flax", "hex": "#D8C0A8"},
            {"name": "Black Noir", "hex": "#121212"},
        ],
        "sizes": ["XS", "S", "M", "L", "XL"],
        "images": [
            "https://images.unsplash.com/photo-1539008835657-9e8e9680c956?w=1000&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1485968579580-b6d095142e6e?w=1000&auto=format&fit=crop",
        ],
    },
    {
        "title": "Pleated Crop Top & Ruffle Midi Skirt Set",
        "description": "Vibrant two-piece matching set cut in lightweight textured cotton with an elasticated off-shoulder crop top and an asymmetric ruffled tiered skirt.",
        "category_slug": "women-sets-skirt-sets",
        "vendor_business": "Adaeze Collections",
        "base_price": Decimal("39500.00"),
        "compare_at_price": Decimal("49000.00"),
        "is_featured": False,
        "size_guide_type": "women_clothing",
        "shop_edit_slugs": ["shop-edits-occasion-wear-party"],
        "colors": [
            {"name": "Tangerine Sunset", "hex": "#FF7518"},
            {"name": "Pistachio", "hex": "#93C572"},
        ],
        "sizes": ["XS", "S", "M", "L", "XL"],
        "images": [
            "https://images.unsplash.com/photo-1485968579580-b6d095142e6e?w=1000&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1583496661160-fb5886a0aaaa?w=1000&auto=format&fit=crop",
        ],
    },
    {
        "title": "Hand-Embellished Silk Boubou Kaftan",
        "description": "Opulent free-flowing Boubou kaftan in pure crepe silk, adorned with hand-applied crystals and glass seed beads around the neckline.",
        "category_slug": "women-outerwear-kaftan",
        "vendor_business": "Adaeze Collections",
        "base_price": Decimal("58000.00"),
        "compare_at_price": Decimal("72000.00"),
        "is_featured": True,
        "size_guide_type": "women_clothing",
        "shop_edit_slugs": ["shop-edits-occasion-wear-evening", "shop-edits-occasion-wear-party"],
        "colors": [
            {"name": "Royal Purple", "hex": "#6A0DAD"},
            {"name": "Marigold Yellow", "hex": "#EAA221"},
            {"name": "Emerald Green", "hex": "#0F766E"},
        ],
        "sizes": ["One Size"],
        "images": [
            "https://images.unsplash.com/photo-1505022610485-0249ba5b3675?w=1000&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1512436991641-6745cdb1723f?w=1000&auto=format&fit=crop",
        ],
    },
    {
        "title": "Printed Raw Silk Floor-Length Kimono Robe",
        "description": "Floor-grazing kimono duster in raw textured silk with wide contrast satin lapels and a detachable matching sash belt.",
        "category_slug": "women-outerwear-kimonos",
        "vendor_business": "Shopsoma Studio",
        "base_price": Decimal("38000.00"),
        "compare_at_price": Decimal("47000.00"),
        "is_featured": False,
        "size_guide_type": "women_clothing",
        "shop_edit_slugs": ["shop-edits-occasion-wear-casual", "shop-edits-occasion-wear-evening"],
        "colors": [
            {"name": "Abstract Indigo", "hex": "#264653"},
            {"name": "Floral Terracotta", "hex": "#E2725B"},
        ],
        "sizes": ["One Size"],
        "images": [
            "https://images.unsplash.com/photo-1558769132-cb1aea3c2226?w=1000&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1505022610485-0249ba5b3675?w=1000&auto=format&fit=crop",
        ],
    },
    {
        "title": "Sculptural Block Heel Nappa Leather Sandals",
        "description": "Modern minimalist sandals crafted in buttery Nappa leather with a rounded sculptural geometric heel and padded leather footbed.",
        "category_slug": "women-shoes-heels",
        "vendor_business": "Adaeze Collections",
        "base_price": Decimal("39000.00"),
        "compare_at_price": Decimal("48000.00"),
        "is_featured": False,
        "size_guide_type": "footwear",
        "shop_edit_slugs": ["shop-edits-occasion-wear-party", "shop-edits-occasion-wear-evening"],
        "colors": [
            {"name": "Metallic Bronze", "hex": "#CD7F32"},
            {"name": "Sandalwood", "hex": "#C2B280"},
            {"name": "Pitch Black", "hex": "#000000"},
        ],
        "sizes": ["37", "38", "39", "40", "41"],
        "images": [
            "https://images.unsplash.com/photo-1543163521-1bf539c55dd2?w=1000&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1535043934128-cf0b28d52f95?w=1000&auto=format&fit=crop",
        ],
    },
    {
        "title": "Pointed Weave Leather Ballerina Flats",
        "description": "Artisan woven leather flats with an elongated pointed toe, cushioned arch support, and non-slip leather sole.",
        "category_slug": "women-shoes-flats",
        "vendor_business": "Shopsoma Studio",
        "base_price": Decimal("28000.00"),
        "compare_at_price": Decimal("35000.00"),
        "is_featured": False,
        "size_guide_type": "footwear",
        "shop_edit_slugs": ["shop-edits-occasion-wear-workwear", "shop-edits-occasion-wear-casual"],
        "colors": [
            {"name": "Almond", "hex": "#EFDECD"},
            {"name": "Onyx Black", "hex": "#111827"},
        ],
        "sizes": ["37", "38", "39", "40", "41"],
        "images": [
            "https://images.unsplash.com/photo-1560343090-f0409e92791a?w=1000&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1549298916-b41d501d3772?w=1000&auto=format&fit=crop",
        ],
    },
    {
        "title": "Sculpting Asymmetric One-Piece Swimsuit",
        "description": "Double-layered Italian chlorine-resistant recycled Econyl swimsuit with subtle compression contouring and an alluring one-shoulder cutout.",
        "category_slug": "women-swimwear",
        "vendor_business": "Shopsoma Studio",
        "base_price": Decimal("22000.00"),
        "compare_at_price": Decimal("28000.00"),
        "is_featured": False,
        "size_guide_type": "women_clothing",
        "shop_edit_slugs": ["shop-edits-occasion-wear-casual"],
        "colors": [
            {"name": "Terracotta", "hex": "#E2725B"},
            {"name": "Obsidian Black", "hex": "#0B0B0B"},
            {"name": "Olive", "hex": "#808000"},
        ],
        "sizes": ["XS", "S", "M", "L"],
        "images": [
            "https://images.unsplash.com/photo-1576871337622-98d48d1cf531?w=1000&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1502716119720-b23a93e5fe1b?w=1000&auto=format&fit=crop",
        ],
    },
    {
        "title": "Pure Mulberry Silk Pyjama & Robe Set",
        "description": "Ultimate sleep luxury: 19-momme pure silk button-up pyjama shirt, drawstring trousers, and matching contrast-piped robe.",
        "category_slug": "women-lingerie-robes-loungewear",
        "vendor_business": "Shopsoma Studio",
        "base_price": Decimal("42000.00"),
        "compare_at_price": Decimal("52000.00"),
        "is_featured": False,
        "size_guide_type": "women_clothing",
        "shop_edit_slugs": ["shop-edits-occasion-wear-casual"],
        "colors": [
            {"name": "Rose Quartz", "hex": "#F7CAC9"},
            {"name": "Champagne", "hex": "#F7E7CE"},
            {"name": "Sage Green", "hex": "#9DC183"},
        ],
        "sizes": ["S", "M", "L", "XL"],
        "images": [
            "https://images.unsplash.com/photo-1582533561751-ef6f6ab93a2e?w=1000&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1566174053879-31528523f8ae?w=1000&auto=format&fit=crop",
        ],
    },

    # ==========================================
    # ACCESSORIES, BAGS & WALLETS
    # ==========================================
    {
        "title": "Structured Boxy Calfskin Crossbody Bag",
        "description": "Architectural box bag crafted from vegetable-tanned full-grain leather with magnetic flap closure, brushed gold hardware, and detachable guitar strap.",
        "category_slug": "women-accessories-bags",
        "vendor_business": "Shopsoma Studio",
        "base_price": Decimal("35000.00"),
        "compare_at_price": Decimal("44000.00"),
        "is_featured": True,
        "size_guide_type": "accessories",
        "shop_edit_slugs": ["shop-edits-occasion-wear-workwear", "shop-edits-occasion-wear-casual"],
        "colors": [
            {"name": "Caramel Tan", "hex": "#C68E17"},
            {"name": "Forest Green", "hex": "#0F766E"},
            {"name": "Onyx Black", "hex": "#111827"},
        ],
        "sizes": ["One Size"],
        "images": [
            "https://images.unsplash.com/photo-1584917865442-de89df76afd3?w=1000&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1590874103328-eac38a683ce7?w=1000&auto=format&fit=crop",
        ],
    },
    {
        "title": "Heritage Handwoven Raffia & Leather Market Tote",
        "description": "Generously proportioned tote woven by artisans using sustainable Madagascan raffia palm and trimmed with vegetable-tanned bridle leather handles.",
        "category_slug": "women-accessories-bags",
        "vendor_business": "Shopsoma Studio",
        "base_price": Decimal("24000.00"),
        "compare_at_price": Decimal("30000.00"),
        "is_featured": False,
        "size_guide_type": "accessories",
        "shop_edit_slugs": ["shop-edits-occasion-wear-casual"],
        "colors": [
            {"name": "Natural Straw/Tan", "hex": "#E3DAC9"},
            {"name": "Natural/Black", "hex": "#2B2B2B"},
        ],
        "sizes": ["One Size"],
        "images": [
            "https://images.unsplash.com/photo-1544816155-12df9643f363?w=1000&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1590874103328-eac38a683ce7?w=1000&auto=format&fit=crop",
        ],
    },
    {
        "title": "Hand-Hammered Brass Choker & Statement Earrings Set",
        "description": "Sculptural jewelry suite handcrafted in reclaimed brass by master metalsmiths. Treated with natural anti-tarnish microcrystalline wax.",
        "category_slug": "women-accessories-jewellery",
        "vendor_business": "Adaeze Collections",
        "base_price": Decimal("18500.00"),
        "compare_at_price": Decimal("24000.00"),
        "is_featured": False,
        "size_guide_type": "accessories",
        "shop_edit_slugs": ["shop-edits-occasion-wear-evening", "shop-edits-occasion-wear-party"],
        "colors": [
            {"name": "Polished Brass", "hex": "#D4AF37"},
            {"name": "Antique Silver", "hex": "#C0C0C0"},
        ],
        "sizes": ["One Size"],
        "images": [
            "https://images.unsplash.com/photo-1599643478518-a784e5dc4c8f?w=1000&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1535632066927-ab7c9ab60908?w=1000&auto=format&fit=crop",
        ],
    },

    # ==========================================
    # BEAUTY & FRAGRANCES
    # ==========================================
    {
        "title": "Oud Royale Extrait de Parfum (100ml)",
        "description": "A regal oriental masterpiece blending aged Cambodian oud, damask rose, smoked amber, and warm bourbon vanilla. 30% pure fragrance oil concentration with 14+ hour longevity.",
        "category_slug": "perfumes",
        "vendor_business": "Shopsoma Studio",
        "base_price": Decimal("45000.00"),
        "compare_at_price": Decimal("55000.00"),
        "is_featured": True,
        "size_guide_type": "accessories",
        "shop_edit_slugs": ["shop-edits-occasion-wear-evening", "shop-edits-occasion-wear-party"],
        "colors": [
            {"name": "Amber Gold", "hex": "#FFBF00"},
        ],
        "sizes": ["One Size"],
        "images": [
            "https://images.unsplash.com/photo-1592945403244-b3fbafd7f539?w=1000&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1547887537-6158d64c35b3?w=1000&auto=format&fit=crop",
        ],
    },
    {
        "title": "Amber & Saffron Niche Eau de Parfum (50ml)",
        "description": "Luminous and seductive Eau de Parfum blending spicy Iranian saffron, crisp red berries, jasmine petals, cedarwood, and rich ambergris.",
        "category_slug": "perfumes",
        "vendor_business": "Shopsoma Studio",
        "base_price": Decimal("32000.00"),
        "compare_at_price": Decimal("39000.00"),
        "is_featured": False,
        "size_guide_type": "accessories",
        "shop_edit_slugs": ["shop-edits-occasion-wear-evening", "shop-edits-occasion-wear-casual"],
        "colors": [
            {"name": "Rose Saffron", "hex": "#E07A5F"},
        ],
        "sizes": ["One Size"],
        "images": [
            "https://images.unsplash.com/photo-1547887537-6158d64c35b3?w=1000&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1592945403244-b3fbafd7f539?w=1000&auto=format&fit=crop",
        ],
    },
    {
        "title": "Whipped Nilotica Shea & Botanical Glow Body Butter",
        "description": "Ultra-rich cold-pressed East African Nilotica shea butter whipped with organic marula oil, rosehip seed oil, and soothing frankincense essential oil. Melts instantly onto skin.",
        "category_slug": "beauty",
        "vendor_business": "Shopsoma Studio",
        "base_price": Decimal("12500.00"),
        "compare_at_price": Decimal("16000.00"),
        "is_featured": False,
        "size_guide_type": "accessories",
        "shop_edit_slugs": ["shop-edits-occasion-wear-casual"],
        "colors": [
            {"name": "Raw Ivory", "hex": "#FFFFF0"},
        ],
        "sizes": ["One Size"],
        "images": [
            "https://images.unsplash.com/photo-1608248597359-56336e4f3a53?w=1000&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1544816155-12df9643f363?w=1000&auto=format&fit=crop",
        ],
    },
]


async def seed_local_products(activate_existing: bool = False):
    """Seed comprehensive demo products into the local development database."""
    verify_local_environment()

    async with AsyncSessionLocal() as session:
        print("[*] Starting local host database seeding...")

        # ---------------------------------------------------------------------
        # 1. Ensure Local Demo Vendors Exist
        # ---------------------------------------------------------------------
        vendors_by_name: Dict[str, Vendor] = {}

        for vdata in VENDORS_SEED:
            user_res = await session.execute(select(User).where(User.email == vdata["email"]))
            vendor_user = user_res.scalar_one_or_none()
            if not vendor_user:
                vendor_user = User(
                    id=uuid.uuid4(),
                    email=vdata["email"],
                    hashed_password=get_password_hash("Vendor123!"),
                    full_name=vdata["name"],
                    role=UserRole.VENDOR,
                    email_verified=True,
                    is_active=True,
                )
                session.add(vendor_user)
                await session.flush()
                print(f"  [+] Created vendor user: {vdata['email']}")

            vendor_res = await session.execute(
                select(Vendor).where(Vendor.user_id == vendor_user.id)
            )
            vendor = vendor_res.scalar_one_or_none()
            if not vendor:
                vendor = Vendor(
                    id=uuid.uuid4(),
                    user_id=vendor_user.id,
                    business_name=vdata["business_name"],
                    business_description=vdata["business_description"],
                    kyc_status=KYCStatus.APPROVED,
                    approved=True,
                    is_onboarding=False,
                    store_active=True,
                    store_deleted_at=None,
                    is_featured_storefront=vdata.get("is_featured_storefront", True),
                )
                session.add(vendor)
                await session.flush()
                print(f"  [+] Created vendor profile: {vdata['business_name']}")
            else:
                vendor.approved = True
                vendor.is_onboarding = False
                vendor.store_active = True
                vendor.store_deleted_at = None

            vendors_by_name[vdata["business_name"]] = vendor

        default_vendor = vendors_by_name["Shopsoma Studio"]

        # ---------------------------------------------------------------------
        # 2. Build Category Lookup Map
        # ---------------------------------------------------------------------
        cats_res = await session.execute(select(Category))
        all_cats = cats_res.scalars().all()
        cat_map = {c.slug: c for c in all_cats}
        print(f"  [OK] Found {len(all_cats)} existing categories in local database")

        # ---------------------------------------------------------------------
        # 3. Seed Products
        # ---------------------------------------------------------------------
        created_count = 0
        updated_count = 0

        for item in PRODUCTS_SEED_DATA:
            existing_res = await session.execute(
                select(Product).options(
                    selectinload(Product.images),
                    selectinload(Product.variants),
                    selectinload(Product.shop_edit_categories),
                ).where(Product.title == item["title"])
            )
            existing_prod = existing_res.scalar_one_or_none()

            # Resolve category
            category = cat_map.get(item["category_slug"])
            if not category and "-" in item["category_slug"]:
                prefix = item["category_slug"].split("-")[0]
                category = cat_map.get(prefix)

            # Resolve shop edit categories
            shop_edit_cats = [cat_map[s] for s in item.get("shop_edit_slugs", []) if s in cat_map]

            # Resolve vendor
            vendor = vendors_by_name.get(item["vendor_business"], default_vendor)

            # Resolve size guide
            size_guide = SIZE_GUIDES.get(item.get("size_guide_type", "men_clothing"))

            if existing_prod:
                await coordinate_catalog_write(session, product_ids=[existing_prod.id], lock_only=True)
                existing_prod.status = ProductStatus.ACTIVE
                existing_prod.moderation_status = ModerationStatus.APPROVED
                existing_prod.base_price = item["base_price"]
                existing_prod.compare_at_price = item["compare_at_price"]
                existing_prod.is_featured = item["is_featured"]
                if category:
                    existing_prod.category_id = category.id
                if shop_edit_cats:
                    existing_prod.shop_edit_categories = shop_edit_cats
                if size_guide:
                    existing_prod.size_guide = size_guide
                updated_count += 1
                continue

            prod_id = uuid.uuid4()
            prod_sku = f"SOMA-{uuid.uuid4().hex[:6].upper()}"

            prod = Product(
                id=prod_id,
                vendor_id=vendor.id,
                category_id=category.id if category else None,
                title=item["title"],
                description=item["description"],
                sku=prod_sku,
                base_price=item["base_price"],
                compare_at_price=item["compare_at_price"],
                currency="NGN",
                status=ProductStatus.ACTIVE,
                is_featured=item["is_featured"],
                product_type=ProductType.VARIABLE,
                moderation_status=ModerationStatus.APPROVED,
                moderation_notes="Demo seeded product for local development",
                size_guide=size_guide,
                total_stock=0,
                shop_edit_categories=shop_edit_cats,
            )
            session.add(prod)
            await session.flush()

            # Add product images
            for idx, img_url in enumerate(item["images"]):
                img = ProductImage(
                    id=uuid.uuid4(),
                    product_id=prod_id,
                    image_url=img_url,
                    thumbnail_url=img_url,
                    alt_text=f"{item['title']} - View {idx + 1}",
                    display_order=idx,
                    is_primary=(idx == 0),
                )
                session.add(img)

            # Add variants, variations, and size_stocks
            total_stock_count = 0

            for color_obj in item["colors"]:
                color_name = color_obj["name"]
                color_hex = color_obj["hex"]

                # Create Variation
                variation_id = uuid.uuid4()
                variation = Variation(
                    id=variation_id,
                    product_id=prod_id,
                    title=color_name,
                    type="color",
                    color_hex=color_hex,
                    price=item["base_price"],
                    sale_price=item["compare_at_price"],
                    inherits_price=True,
                    inherits_sale_price=True,
                    images=item["images"],
                    is_active=True,
                )
                session.add(variation)
                await session.flush()

                seen_sizes_for_variation = set()
                for size_name in item["sizes"]:
                    # Create ProductVariant (legacy architecture support)
                    sku_clean = (
                        f"{item['title'][:3].upper()}-{color_name[:3].upper()}-{size_name}"
                        .replace(" ", "")
                        .replace("/", "")
                    )
                    variant = ProductVariant(
                        id=uuid.uuid4(),
                        product_id=prod_id,
                        size=size_name,
                        color=color_name,
                        color_hex=color_hex,
                        price=item["base_price"],
                        stock=15,
                        sku=f"{sku_clean}-{uuid.uuid4().hex[:4].upper()}",
                        is_available=True,
                        inherits_price=True,
                        inherits_stock=False,
                    )
                    session.add(variant)

                    # Create SizeStock (modern architecture support - unique per variation_id + size)
                    enum_size = SIZE_ENUM_MAP.get(size_name, SizeEnum.ONE_SIZE)
                    if enum_size not in seen_sizes_for_variation:
                        seen_sizes_for_variation.add(enum_size)
                        size_stock = SizeStock(
                            id=uuid.uuid4(),
                            variation_id=variation_id,
                            size=enum_size,
                            stock=15,
                        )
                        session.add(size_stock)
                    total_stock_count += 15

            prod.total_stock = total_stock_count
            created_count += 1
            print(f"  + Added: '{item['title']}' ({item['category_slug']}, NGN {item['base_price']:,.2f}, featured={item['is_featured']})")

        # ---------------------------------------------------------------------
        # 4. Optional: Activate Existing Products
        # ---------------------------------------------------------------------
        if activate_existing:
            print("\n[*] Activating existing draft products...")
            p_res = await session.execute(select(Product.id).where(Product.status != ProductStatus.ACTIVE))
            p_ids = [r[0] for r in p_res.fetchall()]
            if p_ids:
                await coordinate_catalog_write(session, product_ids=p_ids, lock_only=True)
                await session.execute(
                    update(Product)
                    .where(Product.id.in_(p_ids))
                    .values(
                        status=ProductStatus.ACTIVE,
                        moderation_status=ModerationStatus.APPROVED,
                    )
                )
            print("  [OK] All existing products marked ACTIVE and APPROVED")

        await session.commit()

        # ---------------------------------------------------------------------
        # 5. Output Summary
        # ---------------------------------------------------------------------
        total_prods_res = await session.execute(select(Product))
        total_prods = total_prods_res.scalars().all()

        active_prods_res = await session.execute(
            select(Product).where(
                Product.status == ProductStatus.ACTIVE,
                Product.moderation_status == ModerationStatus.APPROVED,
            )
        )
        active_prods = active_prods_res.scalars().all()

        print("\n" + "=" * 60)
        print("[SUCCESS] LOCAL HOST SEEDING COMPLETE!")
        print(f"   * Newly created products: {created_count}")
        print(f"   * Updated existing products: {updated_count}")
        print(f"   * Total products in local database: {len(total_prods)}")
        print(f"   * Active & Approved products ready for local browsing: {len(active_prods)}")
        print("=" * 60)


if __name__ == "__main__":
    should_activate = "--activate-existing" in sys.argv
    asyncio.run(seed_local_products(activate_existing=should_activate))
