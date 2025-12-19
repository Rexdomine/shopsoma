"""Add images directly to products in the database"""
import asyncio
from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.models.product import Product, ProductImage

# Map product titles to their Unsplash images
PRODUCT_IMAGES = {
    "Classic Ankara Print Dress": [
        "https://images.unsplash.com/photo-1595777457583-95e059d581b8?w=800&h=800&fit=crop",
        "https://images.unsplash.com/photo-1596783074918-c84cb06531ca?w=800&h=800&fit=crop"
    ],
    "Men's Traditional Agbada": [
        "https://images.unsplash.com/photo-1622396636049-14c8e0598080?w=800&h=800&fit=crop",
        "https://images.unsplash.com/photo-1622396481329-45e3d35fd4fc?w=800&h=800&fit=crop"
    ],
    "Colorful Gele Head Wrap": [
        "https://images.unsplash.com/photo-1583743814966-8936f5b7be1a?w=800&h=800&fit=crop",
        "https://images.unsplash.com/photo-1618932260643-eee4a2f652cc?w=800&h=800&fit=crop"
    ],
    "Elegant Lace Kaftan": [
        "https://images.unsplash.com/photo-1591369822096-ffd140ec948f?w=800&h=800&fit=crop",
        "https://images.unsplash.com/photo-1612722432474-b971cdcea546?w=800&h=800&fit=crop"
    ],
    "Men's Senator Wear": [
        "https://images.unsplash.com/photo-1593032465175-98b6a1bf1075?w=800&h=800&fit=crop",
        "https://images.unsplash.com/photo-1593032467411-095bafeb6584?w=800&h=800&fit=crop"
    ],
    "Premium Aso Oke Fabric": [
        "https://images.unsplash.com/photo-1610465299996-e5786c2c6167?w=800&h=800&fit=crop",
        "https://images.unsplash.com/photo-1610465299993-e6e4e5a7a7e0?w=800&h=800&fit=crop"
    ],
    "Traditional Fila Cap": [
        "https://images.unsplash.com/photo-1588117305388-c2631a279f82?w=800&h=800&fit=crop",
        "https://images.unsplash.com/photo-1577082893928-345e4286b620?w=800&h=800&fit=crop"
    ],
    "Women's Brocade Wrapper Set": [
        "https://images.unsplash.com/photo-1591369822139-8f1f77e7f019?w=800&h=800&fit=crop",
        "https://images.unsplash.com/photo-1612722432532-1e0d9b3c0e7f?w=800&h=800&fit=crop"
    ],
    "Men's Dashiki Shirt": [
        "https://images.unsplash.com/photo-1602810316693-3667c854239a?w=800&h=800&fit=crop",
        "https://images.unsplash.com/photo-1622396481328-9b1b78cdd9fd?w=800&h=800&fit=crop"
    ],
    "Adire Tie-Dye Fabric": [
        "https://images.unsplash.com/photo-1590736969955-71cc94901144?w=800&h=800&fit=crop",
        "https://images.unsplash.com/photo-1618932260643-eee4a2f652cc?w=800&h=800&fit=crop"
    ]
}


async def add_images():
    async with AsyncSessionLocal() as session:
        # Get all products
        result = await session.execute(select(Product))
        products = result.scalars().all()

        print(f"Found {len(products)} products")

        for product in products:
            # Check if product already has images
            if product.images:
                print(f"  - {product.title}: Already has {len(product.images)} images, skipping")
                continue

            # Get images for this product
            images = PRODUCT_IMAGES.get(product.title, [])

            if not images:
                print(f"  - {product.title}: No images found in mapping")
                continue

            # Add images
            for idx, image_url in enumerate(images):
                product_image = ProductImage(
                    product_id=product.id,
                    image_url=image_url,
                    thumbnail_url=image_url,  # Use same URL for thumbnail
                    alt_text=product.title,
                    display_order=idx,
                    is_primary=(idx == 0)
                )
                session.add(product_image)

            print(f"  - {product.title}: Added {len(images)} images")

        await session.commit()
        print("\n✅ All images added successfully!")


if __name__ == "__main__":
    asyncio.run(add_images())
