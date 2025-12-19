"""
Test script to verify the import fix for require_admin dependency
Run this from the backend directory with venv activated:
    source venv/bin/activate
    python test_import_fix.py
"""
import sys

def test_require_admin_import():
    """Test that require_admin can be imported successfully"""
    try:
        from app.api.dependencies import require_admin, get_current_admin
        print("✓ Successfully imported require_admin from app.api.dependencies")

        # Verify it's an alias
        if require_admin is get_current_admin:
            print("✓ require_admin is correctly aliased to get_current_admin")
        else:
            print("✗ require_admin is not an alias of get_current_admin")
            return False

        return True
    except ImportError as e:
        print(f"✗ Import failed: {e}")
        return False


def test_settings_api_import():
    """Test that settings API can be imported"""
    try:
        from app.api.v1 import settings
        print("✓ Successfully imported settings API module")
        return True
    except ImportError as e:
        print(f"✗ Settings API import failed: {e}")
        return False


def test_main_app_import():
    """Test that main app can be imported"""
    try:
        from app.main import app
        print("✓ Successfully imported main FastAPI app")
        print(f"✓ App title: {app.title}")
        return True
    except ImportError as e:
        print(f"✗ Main app import failed: {e}")
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("Testing Import Fix for require_admin Dependency")
    print("=" * 60)
    print()

    tests = [
        ("require_admin import", test_require_admin_import),
        ("settings API import", test_settings_api_import),
        ("main app import", test_main_app_import),
    ]

    results = []
    for test_name, test_func in tests:
        print(f"Running: {test_name}")
        result = test_func()
        results.append(result)
        print()

    print("=" * 60)
    if all(results):
        print("✓ All tests passed! Server should start successfully.")
        sys.exit(0)
    else:
        print("✗ Some tests failed. Please check the errors above.")
        sys.exit(1)
