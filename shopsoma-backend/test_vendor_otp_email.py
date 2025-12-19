"""Test sending vendor OTP email"""
import asyncio
from app.services.email_service import EmailService

async def test_otp_email():
    email_service = EmailService()

    # Test OTP code
    test_otp = "123456"
    test_email = "dominusparte@gmail.com"

    print(f"Sending test OTP email to {test_email}...")
    print(f"Email service enabled: {email_service.enabled}")

    result = await email_service.send_vendor_otp_email(
        email=test_email,
        otp_code=test_otp,
        expiry_minutes=15
    )

    if result:
        print("✅ Email sent successfully!")
    else:
        print("❌ Failed to send email")

    return result

if __name__ == "__main__":
    asyncio.run(test_otp_email())
