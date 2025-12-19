"""Update product images with working Unsplash URLs"""
import asyncio
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload
from app.core.database import AsyncSessionLocal
from app.models.product import Product, ProductImage

# Map product titles to working Unsplash images
PRODUCT_IMAGES = {
    "Classic Ankara Print Dress": [
        "https://images.unsplash.com/photo-1515372039744-b8f02a3ae446?w=800&h=800&fit=crop",
        "https://images.unsplash.com/photo-1539008835657-9e8e9680c956?w=800&h=800&fit=crop"
    ],
    "Buba and Sokoto Combo": [
        "https://images.unsplash.com/photo-1490481651871-ab68de25d43d?w=800&h=800&fit=crop",
        "https://images.unsplash.com/photo-1503342217505-b0a15ec3261c?w=800&h=800&fit=crop"
    ],
    "Two-Piece Peplum Top and Skirt": [
        "https://images.unsplash.com/photo-1485968579580-b6d095142e6e?w=800&h=800&fit=crop",
        "https://images.unsplash.com/photo-1496747611176-843222e1e57c?w=800&h=800&fit=crop"
    ],
    "Men's Agbada Traditional Outfit": [
        "https://images.unsplash.com/photo-1507680434567-5739c80be1ac?w=800&h=800&fit=crop",
        "https://images.unsplash.com/photo-1594938298603-c8148c4dae35?w=800&h=800&fit=crop"
    ],
    "Men's Senator Wear Complete Set": [
        "https://images.unsplash.com/photo-1620799140408-edc6dcb6d633?w=800&h=800&fit=crop",
        "https://images.unsplash.com/photo-1617127365659-c47fa864d8bc?w=800&h=800&fit=crop"
    ],
    "Native Cap (Fila) Collection": [
        "https://images.unsplash.com/photo-1521572163474-6864f9cf17ab?w=800&h=800&fit=crop",
        "https://images.unsplash.com/photo-1529958030586-3aae4ca485ff?w=800&h=800&fit=crop"
    ],
    "Elegant Gele Head Wrap Set": [
        "https://images.unsplash.com/photo-1487412720507-e7ab37603c6f?w=800&h=800&fit=crop",
        "https://images.unsplash.com/photo-1483985988355-763728e1935b?w=800&h=800&fit=crop"
    ],
    "Aso Ebi Lace Fabric Set": [
        "https://images.unsplash.com/photo-1558769132-cb1aea3c2226?w=800&h=800&fit=crop",
        "https://images.unsplash.com/photo-1525507119028-ed4c629a60a3?w=800&h=800&fit=crop"
    ],
    "Designer Kaftan with Embellishments": [
        "https://images.unsplash.com/photo-1515886657613-9f3515b0c78f?w=800&h=800&fit=crop",
        "https://images.unsplash.com/photo-1505022610485-0249ba5b3675?w=800&h=800&fit=crop"
    ],
    "Maxi Wrapper Skirt with Blouse": [
        "https://images.unsplash.com/photo-1512436991641-6745cdb1723f?w=800&h=800&fit=crop",
        "https://images.unsplash.com/photo-1502716119720-b23a93e5fe1b?w=800&h=800&fit=crop"
    ]
}


async def update_images():
    async with AsyncSessionLocal() as session:
        # Get all products with images
        result = await session.execute(
            select(Product).options(selectinload(Product.images))
        )
        products = result.scalars().all()

        print(f"Updating images for {len(products)} products:\n")

        for product in products:
            # Delete existing images
            if product.images:
                for image in product.images:
                    await session.delete(image)
                await session.flush()
                print(f"  - {product.title}: Deleted {len(product.images)} old images")

            # Get new images for this product
            new_images = PRODUCT_IMAGES.get(product.title, [])

            if not new_images:
                print(f"  - {product.title}: No new images found in mapping")
                continue

            # Add new images
            for idx, image_url in enumerate(new_images):
                product_image = ProductImage(
                    product_id=product.id,
                    image_url=image_url,
                    thumbnail_url=image_url,
                    alt_text=product.title,
                    display_order=idx,
                    is_primary=(idx == 0)
                )
                session.add(product_image)

            print(f"  - {product.title}: Added {len(new_images)} new images")

        await session.commit()
        print("\n✅ All product images updated successfully!")


if __name__ == "__main__":
    asyncio.run(update_images())
