-- Create admin user for Shopsoma Staging
-- Run this SQL directly in Render's PostgreSQL SQL console
--
-- Admin Credentials:
--   Email: admin@shopsoma.com
--   Password: Admin123!Staging
--
-- The password hash below is bcrypt-hashed version of: Admin123!Staging

INSERT INTO users (
    id,
    email,
    hashed_password,
    full_name,
    role,
    is_active,
    email_verified,
    is_guest_created,
    created_at,
    updated_at
)
VALUES (
    gen_random_uuid(),
    'admin@shopsoma.com',
    '$2b$12$agN/xeTgNcWgi/r1Ut/B5uE9DpdUpfLmx5rawBKwLMaRyyDrPjTWS',  -- Password: Admin123!Staging
    'Shopsoma Admin',
    'ADMIN',
    true,
    true,
    false,
    NOW(),
    NOW()
)
ON CONFLICT (email) DO UPDATE SET
    hashed_password = EXCLUDED.hashed_password,
    role = 'ADMIN',
    is_active = true,
    email_verified = true,
    updated_at = NOW();

-- Verify the admin user was created
SELECT
    email,
    full_name,
    role,
    is_active,
    email_verified,
    created_at
FROM users
WHERE email = 'admin@shopsoma.com';
