-- Seed default shipping rates for staging
-- Run this SQL directly in Render's PostgreSQL SQL console or via psql

-- Delete existing rates (optional - only if you want to start fresh)
-- DELETE FROM shipping_rates;

-- Insert default Nigerian shipping rates
INSERT INTO shipping_rates (
    id,
    name,
    description,
    base_rate,
    country,
    state,
    min_order_value,
    max_order_value,
    min_delivery_days,
    max_delivery_days,
    is_active,
    is_default,
    priority,
    created_at,
    updated_at
)
VALUES
-- Lagos Standard Shipping
(
    gen_random_uuid(),
    'Lagos Standard Shipping',
    'Standard delivery within Lagos (3-5 business days)',
    2500.00,  -- ₦2,500
    'Nigeria',
    'Lagos',
    NULL,
    NULL,
    3,
    5,
    true,
    false,
    1,
    NOW(),
    NOW()
),

-- Lagos Express Shipping
(
    gen_random_uuid(),
    'Lagos Express Shipping',
    'Express delivery within Lagos (1-2 business days)',
    4500.00,  -- ₦4,500
    'Nigeria',
    'Lagos',
    NULL,
    NULL,
    1,
    2,
    true,
    false,
    2,
    NOW(),
    NOW()
),

-- Lagos Free Shipping (for orders above ₦50,000)
(
    gen_random_uuid(),
    'Free Shipping (Lagos)',
    'Free delivery within Lagos for orders above ₦50,000',
    0.00,
    'Nigeria',
    'Lagos',
    50000.00,
    NULL,
    3,
    5,
    true,
    true,  -- Default option
    0,  -- Highest priority
    NOW(),
    NOW()
),

-- Nationwide Standard Shipping (All other states)
(
    gen_random_uuid(),
    'Nationwide Standard Shipping',
    'Standard delivery across Nigeria (5-7 business days)',
    3500.00,  -- ₦3,500
    'Nigeria',
    NULL,  -- NULL means all states
    NULL,
    NULL,
    5,
    7,
    true,
    false,
    3,
    NOW(),
    NOW()
),

-- Nationwide Express Shipping
(
    gen_random_uuid(),
    'Nationwide Express Shipping',
    'Express delivery across Nigeria (2-4 business days)',
    6500.00,  -- ₦6,500
    'Nigeria',
    NULL,  -- NULL means all states
    NULL,
    NULL,
    2,
    4,
    true,
    false,
    4,
    NOW(),
    NOW()
)

ON CONFLICT DO NOTHING;

-- Verify the shipping rates were created
SELECT
    id,
    name,
    base_rate,
    country,
    state,
    is_active,
    is_default,
    priority,
    min_delivery_days || '-' || max_delivery_days AS delivery_days
FROM shipping_rates
ORDER BY priority ASC, base_rate ASC;
