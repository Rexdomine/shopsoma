"""Update all products with proper color/size variations and size guides"""
import asyncio
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload
from app.core.database import AsyncSessionLocal
from app.models.product import Product, ProductVariant

# Size guide for different product types
SIZE_GUIDES = {
    "women_clothing": {
        "gender": "Women's",
        "title": "Women's Size Guide",
        "subtitle": "African Fashion Sizing",
        "rows": [
            {"label": "L", "standard": "Large", "measurement": "Bust: 36-38\" / 91-96cm, Waist: 28-30\" / 71-76cm"},
            {"label": "XL", "standard": "Extra Large", "measurement": "Bust: 40-42\" / 101-106cm, Waist: 32-34\" / 81-86cm"},
            {"label": "XXL", "standard": "Double XL", "measurement": "Bust: 44-46\" / 111-116cm, Waist: 36-38\" / 91-96cm"}
        ]
    },
    "men_clothing": {
        "gender": "Men's",
        "title": "Men's Size Guide",
        "subtitle": "Traditional African Wear Sizing",
        "rows": [
            {"label": "L", "standard": "Large", "measurement": "Chest: 42-44\" / 106-111cm, Waist: 34-36\" / 86-91cm"},
            {"label": "XL", "standard": "Extra Large", "measurement": "Chest: 46-48\" / 116-121cm, Waist: 38-40\" / 96-101cm"},
            {"label": "XXL", "standard": "Double XL", "measurement": "Chest: 50-52\" / 127-132cm, Waist: 42-44\" / 106-111cm"}
        ]
    },
    "accessories": {
        "gender": "Unisex",
        "title": "Accessory Size Guide",
        "subtitle": "Traditional Accessories",
        "rows": [
            {"label": "L", "standard": "Large", "measurement": "Fits most adults"},
            {"label": "XL", "standard": "Extra Large", "measurement": "Fits larger sizes"},
            {"label": "XXL", "standard": "Double XL", "measurement": "Fits extra large sizes"}
        ]
    },
    "fabric": {
        "gender": "Unisex",
        "title": "Fabric Size Guide",
        "subtitle": "Fabric Measurements",
        "rows": [
            {"label": "L", "standard": "5 Yards", "measurement": "5 yards / 4.5 meters"},
            {"label": "XL", "standard": "6 Yards", "measurement": "6 yards / 5.5 meters"},
            {"label": "XXL", "standard": "7 Yards", "measurement": "7 yards / 6.4 meters"}
        ]
    }
}

# Product categorization and color schemes
PRODUCT_CONFIGS = {
    "Classic Ankara Print Dress": {
        "type": "women_clothing",
        "colors": [
            {"name": "Red Multi", "hex": "#DC143C"},
            {"name": "Blue Multi", "hex": "#4169E1"},
            {"name": "Green Multi", "hex": "#228B22"}
        ]
    },
    "Buba and Sokoto Combo": {
        "type": "men_clothing",
        "colors": [
            {"name": "Royal Blue", "hex": "#4169E1"},
            {"name": "Navy", "hex": "#000080"},
            {"name": "White", "hex": "#FFFFFF"}
        ]
    },
    "Two-Piece Peplum Top and Skirt": {
        "type": "women_clothing",
        "colors": [
            {"name": "Burgundy", "hex": "#800020"},
            {"name": "Emerald", "hex": "#50C878"},
            {"name": "Gold", "hex": "#FFD700"}
        ]
    },
    "Men's Agbada Traditional Outfit": {
        "type": "men_clothing",
        "colors": [
            {"name": "White", "hex": "#FFFFFF"},
            {"name": "Cream", "hex": "#FFFDD0"},
            {"name": "Black", "hex": "#000000"}
        ]
    },
    "Men's Senator Wear Complete Set": {
        "type": "men_clothing",
        "colors": [
            {"name": "Navy", "hex": "#000080"},
            {"name": "Charcoal", "hex": "#36454F"},
            {"name": "Brown", "hex": "#8B4513"}
        ]
    },
    "Native Cap (Fila) Collection": {
        "type": "accessories",
        "colors": [
            {"name": "Black", "hex": "#000000"},
            {"name": "Brown", "hex": "#8B4513"},
            {"name": "Navy", "hex": "#000080"}
        ]
    },
    "Elegant Gele Head Wrap Set": {
        "type": "accessories",
        "colors": [
            {"name": "Gold", "hex": "#FFD700"},
            {"name": "Purple", "hex": "#800080"},
            {"name": "Coral", "hex": "#FF7F50"}
        ]
    },
    "Aso Ebi Lace Fabric Set": {
        "type": "fabric",
        "colors": [
            {"name": "Navy", "hex": "#000080"},
            {"name": "Wine", "hex": "#722F37"},
            {"name": "Peach", "hex": "#FFE5B4"}
        ]
    },
    "Designer Kaftan with Embellishments": {
        "type": "women_clothing",
        "colors": [
            {"name": "Black Gold", "hex": "#000000"},
            {"name": "Royal Blue", "hex": "#4169E1"},
            {"name": "Emerald", "hex": "#50C878"}
        ]
    },
    "Maxi Wrapper Skirt with Blouse": {
        "type": "women_clothing",
        "colors": [
            {"name": "Ankara Multi", "hex": "#DC143C"},
            {"name": "Blue Print", "hex": "#4169E1"},
            {"name": "Yellow Print", "hex": "#FFD700"}
        ]
    }
}

SIZES = ["L", "XL", "XXL"]


async def update_products():
    async with AsyncSessionLocal() as session:
        # Get all products with variants
        result = await session.execute(
            select(Product).options(selectinload(Product.variants))
        )
        products = result.scalars().all()

        print(f"Updating {len(products)} products with proper variations and size guides:\n")

        for product in products:
            # Get product configuration
            config = PRODUCT_CONFIGS.get(product.title)
            if not config:
                print(f"  ⚠️  {product.title}: No configuration found, skipping")
                continue

            # Delete existing variants
            if product.variants:
                for variant in product.variants:
                    await session.delete(variant)
                await session.flush()
                print(f"  - {product.title}: Deleted {len(product.variants)} old variants")

            # Add size guide
            size_guide_type = config["type"]
            product.size_guide = SIZE_GUIDES[size_guide_type]

            # Create new variants (3 colors × 3 sizes = 9 variants)
            colors = config["colors"]
            variants_created = 0

            for color_idx, color in enumerate(colors):
                for size_idx, size in enumerate(SIZES):
                    # Calculate price variation (base + color premium + size premium)
                    color_premium = color_idx * 500  # Each color adds ₦500
                    size_premium = size_idx * 1000   # L=0, XL=+1000, XXL=+2000
                    variant_price = float(product.base_price) + color_premium + size_premium

                    # Generate SKU
                    sku_prefix = ''.join([word[0].upper() for word in product.title.split()[:3]])
                    sku = f"{sku_prefix}-{color['name'].replace(' ', '').upper()[:4]}-{size}"

                    # Create variant
                    variant = ProductVariant(
                        product_id=product.id,
                        size=size,
                        color=color["name"],
                        color_hex=color["hex"],
                        price=variant_price,
                        stock=15 + (size_idx * 5),  # L=15, XL=20, XXL=25
                        sku=sku,
                        is_available=True
                    )
                    session.add(variant)
                    variants_created += 1

            print(f"  ✅ {product.title}: Created {variants_created} variants ({len(colors)} colors × {len(SIZES)} sizes) + size guide")

        await session.commit()
        print("\n✅ All products updated successfully!")

        # Verify updates
        print("\n📊 Verification:")
        result = await session.execute(
            select(Product).options(selectinload(Product.variants))
        )
        products = result.scalars().all()

        for product in products:
            size_guide_status = "✓ Has size guide" if product.size_guide else "✗ No size guide"
            print(f"  - {product.title}: {len(product.variants)} variants, {size_guide_status}")


if __name__ == "__main__":
    asyncio.run(update_products())
