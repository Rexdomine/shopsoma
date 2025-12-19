#!/usr/bin/env python3
"""
Add base "White" variant to Angel White product for testing
"""
import uuid
from sqlalchemy import create_engine, text
from decimal import Decimal

# Database connection
DATABASE_URL = "postgresql://shopsoma:shopsoma_dev_password@localhost:5432/shopsoma_db"
engine = create_engine(DATABASE_URL)

product_id = "9ac646a0-9cca-49f9-96cb-09382c1cf650"

# Create a base "White" variant
variant_id = str(uuid.uuid4())

insert_query = text("""
    INSERT INTO product_variants (
        id, product_id, size, color, color_hex, price, stock, sku, is_available, created_at, updated_at
    ) VALUES (
        :id, :product_id, 'M', 'White', '#FFFFFF', 150.00, 100, NULL, true, NOW(), NOW()
    )
    ON CONFLICT (id) DO NOTHING
""")

with engine.connect() as conn:
    conn.execute(insert_query, {
        "id": variant_id,
        "product_id": product_id
    })
    conn.commit()
    print(f"✅ Added base 'White' variant (ID: {variant_id})")
    print("   Size: M, Color: White, Stock: 100, Price: $150")

# Verify
with engine.connect() as conn:
    result = conn.execute(text("""
        SELECT color, size, stock, price
        FROM product_variants
        WHERE product_id = :product_id AND color = 'White'
    """), {"product_id": product_id})

    rows = result.fetchall()
    if rows:
        print(f"\n✅ Verification: Found {len(rows)} White variant(s)")
        for row in rows:
            print(f"   {row[0]} / {row[1]} - Stock: {row[2]}, Price: ${row[3]}")
    else:
        print("\n❌ Variant not found!")

print("\n✅ Base color 'White' is now available in product options")
