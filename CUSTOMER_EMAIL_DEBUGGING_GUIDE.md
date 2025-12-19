# Customer Email Debugging Guide

**Date**: December 17, 2025
**Issue**: Customers not receiving emails for status changes
**Solution**: Added comprehensive logging to track email notification flow

---

## What Was Changed

### File Modified
- `shopsoma-backend/app/services/order_notification_service.py`

### Changes Made
1. **Added logging import** (line 7):
   ```python
   import logging
   ```

2. **Added logger instance** (line 16):
   ```python
   logger = logging.getLogger(__name__)
   ```

3. **Enhanced `notify_status_change()` method** (lines 161-180):
   - Logs when notification process starts
   - Logs vendor notification attempts and results
   - Logs customer notification attempts and results
   - Logs summary of both notifications

4. **Enhanced `_notify_customer()` method** (lines 243-298):
   - Logs when method is called with order and status
   - Logs status config lookup results
   - Logs if email sending is enabled/disabled for the status
   - Logs customer existence and email validation
   - Logs email content building
   - Logs email service call with customer details
   - Logs email sending result (success or failure)
   - Logs detailed exceptions with stack traces

---

## How to Debug Customer Emails

### Step 1: Start Backend with Visible Logs

```bash
cd shopsoma-backend
. venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

**Important**: Do NOT run in background - you need to see the logs!

### Step 2: Trigger a Status Change

1. Open admin dashboard: http://localhost:5174/admin/orders
2. Login with admin credentials
3. Click "View" on any order
4. Change status to "In Transit" (or any customer-facing status)
5. Watch the backend terminal

### Step 3: Analyze the Logs

You should see a sequence of log messages like this:

#### **Expected Successful Flow**:
```
INFO: 📢 notify_status_change called for order ORD-12345: status=in_transit
INFO: 👔 Attempting to notify vendors for order ORD-12345
INFO: 👔 Vendor notification result: True
INFO: 👤 Attempting to notify customer for order ORD-12345
INFO: 🔔 _notify_customer called for order ORD-12345, status: in_transit
INFO: ✅ Customer email enabled for status: in_transit - 'In Transit'
INFO: 📧 Preparing to send customer email to: customer@example.com
INFO: 📝 Email content built, length: 3245 chars
INFO: 🚀 Calling email service to send to customer@example.com (name: John Doe)
INFO: Sending email to customer@example.com (name: John Doe), subject: 'Order ORD-12345: In Transit'
INFO: ✅ Email sent successfully to customer@example.com. Message ID: <abc123>
INFO: ✅ Customer email sent successfully to customer@example.com
INFO: 👤 Customer notification result: True
INFO: 📊 Notification summary for order ORD-12345: vendor=True, customer=True
```

#### **Common Failure Scenarios**:

**Scenario 1: Email Sending Disabled for Status**
```
INFO: 🔔 _notify_customer called for order ORD-12345, status: preparing_for_pickup
INFO: ⏭️  Customer email sending disabled for status: preparing_for_pickup
INFO: 👤 Customer notification result: False
```
**Solution**: This is expected behavior. Customer emails are only sent for specific statuses.

**Scenario 2: No Customer Found**
```
INFO: 🔔 _notify_customer called for order ORD-12345, status: in_transit
INFO: ✅ Customer email enabled for status: in_transit - 'In Transit'
ERROR: ❌ No customer found for order ORD-12345
INFO: 👤 Customer notification result: False
```
**Solution**: Order has no customer relationship. Check database integrity.

**Scenario 3: Customer Has No Email**
```
INFO: 🔔 _notify_customer called for order ORD-12345, status: in_transit
INFO: ✅ Customer email enabled for status: in_transit - 'In Transit'
ERROR: ❌ Customer abc-123 has no email for order ORD-12345
INFO: 👤 Customer notification result: False
```
**Solution**: Customer record has null email. Update customer data.

**Scenario 4: Email Service Disabled**
```
INFO: 🔔 _notify_customer called for order ORD-12345, status: in_transit
INFO: ✅ Customer email enabled for status: in_transit - 'In Transit'
INFO: 📧 Preparing to send customer email to: customer@example.com
INFO: 📝 Email content built, length: 3245 chars
INFO: 🚀 Calling email service to send to customer@example.com (name: John Doe)
WARNING: Email send skipped (to: customer@example.com, subject: 'Order ORD-12345: In Transit'): Brevo enabled=False, api_instance=None, BREVO_API_KEY=NOT SET
INFO: ⚠️  Email service returned False for customer@example.com
INFO: 👤 Customer notification result: False
```
**Solution**: Brevo API key not configured. Check `.env` file.

**Scenario 5: Email Service Error**
```
INFO: 🔔 _notify_customer called for order ORD-12345, status: in_transit
INFO: ✅ Customer email enabled for status: in_transit - 'In Transit'
INFO: 📧 Preparing to send customer email to: customer@example.com
INFO: 📝 Email content built, length: 3245 chars
INFO: 🚀 Calling email service to send to customer@example.com (name: John Doe)
ERROR: Brevo API error: Invalid API key
ERROR: ❌ Failed to notify customer for order abc-123: Brevo API error
    [Full stack trace...]
INFO: 👤 Customer notification result: False
```
**Solution**: Brevo API key is invalid. Get valid key from Brevo dashboard.

---

## Customer Email Status Configuration

### Statuses That Send Customer Emails
- ✅ **ORDER_RECEIVED**: "Order Confirmed"
- ✅ **PICKED_UP**: "Order Dispatched"
- ✅ **IN_TRANSIT**: "In Transit"
- ✅ **OUT_FOR_DELIVERY**: "Out for Delivery"
- ✅ **DELIVERED**: "Delivered Successfully"
- ✅ **DELIVERY_FAILED**: "Delivery Attempt Failed"
- ✅ **RETURNED**: "Order Returned"
- ✅ **CANCELLED**: "Order Cancelled"

### Statuses That Do NOT Send Customer Emails
- ❌ **PREPARING_FOR_PICKUP**: Internal vendor status
- ❌ **PICKUP_SCHEDULED**: Internal vendor status

---

## Quick Checks

### 1. Check if Customer Has Email
```bash
cd shopsoma-backend
. venv/bin/activate
python -c "
from app.models.order import Order
from app.core.database import get_sync_db
from sqlalchemy.orm import selectinload

db = next(get_sync_db())
order = db.query(Order).options(selectinload(Order.customer)).first()
print(f'Order: {order.order_number}')
print(f'Customer: {order.customer}')
print(f'Customer Email: {order.customer.email if order.customer else \"NO CUSTOMER\"}')
"
```

### 2. Check Brevo Configuration
```bash
cd shopsoma-backend
cat .env | grep BREVO
```

Expected output:
```
BREVO_API_KEY=xkeysib-abc123...
BREVO_SENDER_EMAIL=noreply@shopsoma.com
BREVO_SENDER_NAME=Shopsoma
```

### 3. Test Email Service Directly
```bash
cd shopsoma-backend
. venv/bin/activate
python -c "
import asyncio
from app.services.email_service import EmailService

async def test():
    service = EmailService()
    result = await service.send_email(
        to_email='your-test-email@example.com',
        to_name='Test User',
        subject='Test Email',
        html_content='<h1>This is a test</h1><p>If you see this, email service works!</p>'
    )
    print(f'Email sent: {result}')

asyncio.run(test())
"
```

---

## Testing Checklist

### Pre-Test Setup
- [ ] Backend running with visible logs (NOT in background)
- [ ] Test order has valid customer with email
- [ ] Brevo API key configured in `.env`
- [ ] Test email account accessible

### Test Customer Emails for Each Status

**1. In Transit**
- [ ] Change order status to "In Transit"
- [ ] Check logs for: `✅ Customer email enabled for status: in_transit`
- [ ] Check logs for: `✅ Customer email sent successfully to`
- [ ] Check email inbox (and spam folder)
- [ ] **Expected**: Customer receives "In Transit" email

**2. Out for Delivery**
- [ ] Change order status to "Out for Delivery"
- [ ] Check logs for customer email success
- [ ] Check email inbox
- [ ] **Expected**: Customer receives "Out for Delivery" email

**3. Delivered**
- [ ] Change order status to "Delivered"
- [ ] Check logs for customer email success
- [ ] Check email inbox
- [ ] **Expected**: Customer receives "Delivered Successfully" email

**4. Delivery Failed**
- [ ] Change order status to "Delivery Failed"
- [ ] Check logs for customer email success
- [ ] Check email inbox
- [ ] **Expected**: Customer receives "Delivery Attempt Failed" email

**5. Returned**
- [ ] Change order status to "Returned"
- [ ] Check logs for customer email success
- [ ] Check email inbox
- [ ] **Expected**: Customer receives "Order Returned" email

**6. Cancelled**
- [ ] Change order status to "Cancelled"
- [ ] Check logs for customer email success
- [ ] Check email inbox
- [ ] **Expected**: Customer receives "Order Cancelled" email

### Verify No Emails for Internal Statuses

**7. Preparing for Pickup**
- [ ] Change order status to "Preparing for Pickup"
- [ ] Check logs for: `⏭️  Customer email sending disabled for status: preparing_for_pickup`
- [ ] Check email inbox
- [ ] **Expected**: NO customer email sent (this is correct)

**8. Pickup Scheduled**
- [ ] Change order status to "Pickup Scheduled"
- [ ] Check logs show email disabled for this status
- [ ] Check email inbox
- [ ] **Expected**: NO customer email sent (this is correct)

---

## Troubleshooting

### Problem: No Logs Appearing

**Check**:
1. Backend actually running? `lsof -i :8000`
2. Logs redirected? Make sure NOT using `> /dev/null 2>&1`
3. Log level configured? Check FastAPI logging config

**Solution**:
```bash
# Stop all background processes
pkill -f uvicorn

# Start with explicit logging
cd shopsoma-backend
. venv/bin/activate
uvicorn app.main:app --reload --port 8000 --log-level info
```

### Problem: Logs Show "Email Sent" But Nothing in Inbox

**Check**:
1. Spam folder
2. Promotions tab (Gmail)
3. Brevo dashboard for delivery status
4. Email address is correct (typos?)

**Solution**:
Go to https://www.brevo.com/
- Login
- Navigate to "Statistics" → "Email"
- Check recent sends
- Look for bounces, blocks, or delivery failures

### Problem: "Brevo API Error"

**Common Errors**:

**Invalid API Key**:
```
ERROR: Brevo API error: Invalid API key
```
**Solution**: Get valid API key from Brevo dashboard, update `.env`

**Rate Limit Exceeded**:
```
ERROR: Brevo API error: Too many requests
```
**Solution**: Wait a minute, or upgrade Brevo plan

**Email Not Verified**:
```
ERROR: Brevo API error: Sender email not verified
```
**Solution**: Verify sender email in Brevo dashboard

---

## Expected Log Output Example

Here's what a complete successful customer email flow looks like:

```
INFO:     127.0.0.1:62894 - "PATCH /api/v1/admin/orders/790ff9e3-5e24-490c-bac2-849200a4ddfe/status HTTP/1.1" 200 OK
INFO: 📢 notify_status_change called for order ORD-2024-12345: status=in_transit
INFO: 👔 Attempting to notify vendors for order ORD-2024-12345
INFO: 👔 Vendor notification result: True
INFO: 👤 Attempting to notify customer for order ORD-2024-12345
INFO: 🔔 _notify_customer called for order ORD-2024-12345, status: in_transit
INFO: ✅ Customer email enabled for status: in_transit - 'In Transit'
INFO: 📧 Preparing to send customer email to: john.doe@example.com
INFO: 📝 Email content built, length: 3458 chars
INFO: 🚀 Calling email service to send to john.doe@example.com (name: John Doe)
INFO: Sending email to john.doe@example.com (name: John Doe), subject: 'Order ORD-2024-12345: In Transit'
INFO: ✅ Email sent successfully to john.doe@example.com. Message ID: <20251217120456.12345.67890@smtp-relay.brevo.com>
INFO: ✅ Customer email sent successfully to john.doe@example.com
INFO: 👤 Customer notification result: True
INFO: 📊 Notification summary for order ORD-2024-12345: vendor=True, customer=True
```

---

## Next Steps After Testing

1. **If emails are working**:
   - Deploy to staging
   - Test with real customer emails
   - Monitor Brevo dashboard for delivery rates
   - Deploy to production

2. **If emails still not working**:
   - Share the exact log output with the team
   - Check Brevo dashboard for errors
   - Verify environment configuration
   - Consider alternative email provider if Brevo issues persist

---

## Support Resources

- **Brevo Documentation**: https://developers.brevo.com/
- **Brevo Dashboard**: https://app.brevo.com/
- **Email Service Code**: `shopsoma-backend/app/services/email_service.py`
- **Notification Service Code**: `shopsoma-backend/app/services/order_notification_service.py`

---

**The comprehensive logging is now in place!** 🎉
Run the backend and test a status change to see exactly what's happening with customer emails.
