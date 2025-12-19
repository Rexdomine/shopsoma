#!/bin/bash

# Email Notifications Testing Script
# Tests email functionality for order status updates

echo "📧 Email Notifications Testing Guide"
echo "======================================"
echo ""
echo "This script will help you debug email notifications."
echo ""

# Check if backend is running
if lsof -Pi :8000 -sTCP:LISTEN -t >/dev/null ; then
    echo "⚠️  Backend is already running on port 8000"
    echo ""
    echo "To test email notifications properly, you need to:"
    echo "1. Stop the current backend (it may be hiding logs)"
    echo "2. Start it again with visible logs"
    echo ""
    echo "Run these commands:"
    echo ""
    echo "  # Stop current backend"
    echo "  pkill -f uvicorn"
    echo ""
    echo "  # Start backend with visible logs"
    echo "  cd shopsoma-backend"
    echo "  . venv/bin/activate"
    echo "  uvicorn app.main:app --reload --port 8000"
    echo ""
    echo "Then watch for these log messages when updating order status:"
    echo "  ✅ 'Email sent successfully to customer@example.com'"
    echo "  ✅ 'Email sent successfully to vendor@example.com'"
    echo "  ❌ 'WARNING: Email send skipped'"
    echo "  ❌ 'ERROR: Failed to send email'"
    echo ""
else
    echo "✅ Port 8000 is free"
    echo ""
    echo "Starting backend with visible logs..."
    echo ""

    cd shopsoma-backend

    # Activate virtual environment
    if [ -f "venv/bin/activate" ]; then
        . venv/bin/activate
        echo "✅ Virtual environment activated"
    else
        echo "❌ Virtual environment not found!"
        echo "Please run: python -m venv venv"
        exit 1
    fi

    # Check if Brevo SDK is installed
    python -c "import sib_api_v3_sdk" 2>/dev/null
    if [ $? -eq 0 ]; then
        echo "✅ Brevo SDK is installed"
    else
        echo "❌ Brevo SDK not installed!"
        echo "Please run: pip install sib-api-v3-sdk"
        exit 1
    fi

    # Check environment variables
    if grep -q "BREVO_API_KEY" .env; then
        echo "✅ BREVO_API_KEY found in .env"
    else
        echo "❌ BREVO_API_KEY not found in .env!"
        exit 1
    fi

    echo ""
    echo "🚀 Starting backend server..."
    echo ""
    echo "Watch for email-related log messages below:"
    echo "==========================================="
    echo ""

    # Start uvicorn with visible output
    uvicorn app.main:app --reload --port 8000
fi

echo ""
echo "Testing Steps:"
echo "=============="
echo ""
echo "1. Open admin dashboard:"
echo "   http://localhost:5174/admin/orders"
echo ""
echo "2. Login with:"
echo "   Email: admin@shopsoma.com"
echo "   Password: Admin123"
echo ""
echo "3. Click 'View' on any order"
echo ""
echo "4. Change status (e.g., Order Received → In Transit)"
echo ""
echo "5. Watch this terminal for email logs"
echo ""
echo "6. Check your email inbox (including spam folder)"
echo ""
echo "7. Test both directions:"
echo "   - Forward: Order Received → Delivered"
echo "   - Backward: Delivered → In Transit"
echo ""
echo "Expected Results:"
echo "================="
echo ""
echo "✅ Terminal shows 'Email sent successfully'"
echo "✅ Email appears in inbox or spam"
echo "✅ Email contains order details and status"
echo ""
echo "If No Emails:"
echo "============="
echo ""
echo "1. Check Brevo dashboard: https://www.brevo.com/"
echo "2. Navigate to Statistics → Email"
echo "3. Look for recent send attempts"
echo "4. Check for bounces or errors"
echo ""
echo "5. Verify API key is valid:"
echo "   - Not expired"
echo "   - Not rate-limited"
echo "   - Has permission to send emails"
echo ""
