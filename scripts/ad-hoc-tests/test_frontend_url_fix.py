#!/usr/bin/env python3
"""
Test script to verify FRONTEND_URL configuration fix
"""
import sys
import os

# Add backend to path
sys.path.insert(0, '/Users/rex/Documents/Shopsoma/shopsoma-backend')

def test_frontend_url():
    """Test that settings.FRONTEND_URL is accessible"""
    try:
        from app.core.config import Settings

        # Create settings instance
        settings = Settings()

        print("✅ Settings loaded successfully")
        print(f"   FRONTEND_BASE_URL: {settings.FRONTEND_BASE_URL}")

        # Test the property
        frontend_url = settings.FRONTEND_URL
        print(f"✅ FRONTEND_URL property accessible: {frontend_url}")

        # Verify they match
        assert settings.FRONTEND_URL == settings.FRONTEND_BASE_URL, "URLs don't match!"
        print("✅ FRONTEND_URL equals FRONTEND_BASE_URL")

        # Test URL construction (as used in email service)
        product_id = "test-product-123"
        product_link = f"{settings.FRONTEND_URL}/vendor/products/{product_id}/view"
        print(f"✅ Example product link: {product_link}")

        dashboard_link = f"{settings.FRONTEND_URL}/vendor/products"
        print(f"✅ Example dashboard link: {dashboard_link}")

        print("\n🎉 All tests passed! Email service should now work correctly.")
        return True

    except AttributeError as e:
        print(f"❌ AttributeError: {e}")
        print("   The FRONTEND_URL property may not be defined correctly.")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_frontend_url()
    sys.exit(0 if success else 1)
