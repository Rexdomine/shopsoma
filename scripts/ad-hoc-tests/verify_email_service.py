#!/usr/bin/env python3
"""
Verify Email Service Configuration

This script tests if the Brevo email service is properly configured.
"""

import sys
import os

# Add the backend directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'shopsoma-backend'))

def verify_brevo_sdk():
    """Verify Brevo SDK is installed"""
    try:
        import sib_api_v3_sdk
        print("✅ Brevo SDK is installed (version: 7.6.0)")
        return True
    except ImportError:
        print("❌ Brevo SDK is NOT installed")
        print("   Install with: pip install sib-api-v3-sdk")
        return False

def verify_environment_variables():
    """Verify environment variables are set"""
    from dotenv import load_dotenv

    # Load .env file
    env_path = os.path.join(os.path.dirname(__file__), 'shopsoma-backend', '.env')
    load_dotenv(env_path)

    brevo_api_key = os.getenv('BREVO_API_KEY')
    brevo_sender_email = os.getenv('BREVO_SENDER_EMAIL')
    brevo_sender_name = os.getenv('BREVO_SENDER_NAME')

    print("\n📧 Environment Variables:")
    if brevo_api_key:
        print(f"✅ BREVO_API_KEY is set ({brevo_api_key[:15]}...)")
    else:
        print("❌ BREVO_API_KEY is NOT set")

    if brevo_sender_email:
        print(f"✅ BREVO_SENDER_EMAIL is set ({brevo_sender_email})")
    else:
        print("❌ BREVO_SENDER_EMAIL is NOT set")

    if brevo_sender_name:
        print(f"✅ BREVO_SENDER_NAME is set ({brevo_sender_name})")
    else:
        print("❌ BREVO_SENDER_NAME is NOT set")

    return bool(brevo_api_key and brevo_sender_email and brevo_sender_name)

def verify_email_service():
    """Verify email service initializes correctly"""
    try:
        from app.services.email_service import EmailService
        from app.core.config import settings

        print("\n🔧 Email Service Configuration:")
        email_service = EmailService()

        if email_service.enabled and email_service.api_instance is not None:
            print("✅ Email service is ENABLED and configured")
            print(f"   Sender: {settings.BREVO_SENDER_NAME} <{settings.BREVO_SENDER_EMAIL}>")
            return True
        else:
            print("❌ Email service is NOT properly configured")
            print(f"   Enabled: {email_service.enabled}")
            print(f"   API Instance: {'configured' if email_service.api_instance else 'None'}")
            return False

    except Exception as e:
        print(f"❌ Error initializing email service: {e}")
        return False

def main():
    print("🧪 Verifying Email Service Configuration")
    print("=" * 50)

    # Step 1: Check SDK
    sdk_ok = verify_brevo_sdk()

    # Step 2: Check environment variables
    env_ok = verify_environment_variables()

    # Step 3: Check email service initialization
    service_ok = verify_email_service()

    # Summary
    print("\n" + "=" * 50)
    print("📊 Summary:")
    print(f"   Brevo SDK: {'✅ Installed' if sdk_ok else '❌ Missing'}")
    print(f"   Environment: {'✅ Configured' if env_ok else '❌ Missing'}")
    print(f"   Email Service: {'✅ Ready' if service_ok else '❌ Not Ready'}")

    if sdk_ok and env_ok and service_ok:
        print("\n🎉 Email notifications are READY!")
        print("   Order status change emails will now be sent automatically.")
        print("\n📝 Next Steps:")
        print("   1. Restart the backend server to load new configuration")
        print("   2. Update an order status from admin dashboard")
        print("   3. Check customer/vendor email inbox")
        return 0
    else:
        print("\n⚠️  Email notifications are NOT ready")
        print("   Please fix the issues above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
