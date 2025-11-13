"""Clean up duplicate products, keeping only the first 10"""
import asyncio
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from app.core.database import AsyncSessionLocal
from app.models.product import Product


async def cleanup():
    async with AsyncSessionLocal() as session:
        # Get all products grouped by title
        result = await session.execute(
            select(Product).options(selectinload(Product.variants), selectinload(Product.images))
        )
        products = result.scalars().all()

        # Group by title
        products_by_title = {}
        for product in products:
            if product.title not in products_by_title:
                products_by_title[product.title] = []
            products_by_title[product.title].append(product)

        print(f"Found {len(products)} total products in {len(products_by_title)} unique titles\n")

        deleted_count = 0
        for title, product_list in products_by_title.items():
            if len(product_list) > 1:
                # Keep the first one, delete the rest
                to_keep = product_list[0]
                to_delete = product_list[1:]

                print(f"  {title}: Keeping 1, deleting {len(to_delete)} duplicates")

                for product in to_delete:
                    await session.delete(product)
                    deleted_count += 1

        if deleted_count > 0:
            await session.commit()
            print(f"\n✅ Deleted {deleted_count} duplicate products")
        else:
            print("\n✅ No duplicates found!")

        # Show remaining products
        result = await session.execute(select(func.count(Product.id)))
        remaining = result.scalar()
        print(f"\nRemaining products: {remaining}")


if __name__ == "__main__":
    asyncio.run(cleanup())
