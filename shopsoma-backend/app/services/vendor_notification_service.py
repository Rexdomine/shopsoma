"""Vendor notification email service"""
from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import Vendor, VendorNotification, User
from app.services.email_service import EmailService


class VendorNotificationService:
    """Service for sending vendor notifications via email"""

    def __init__(self, email_service: EmailService):
        self.email_service = email_service

    async def send_order_notification(
        self,
        db: AsyncSession,
        vendor_id: str,
        order_number: str,
        product_title: str,
        quantity: int,
        vendor_payout: float,
        scheduled_pickup_date: datetime
    ):
        """
        Send order placed notification to vendor

        Args:
            db: Database session
            vendor_id: Vendor ID
            order_number: Order number
            product_title: Product title
            quantity: Quantity ordered
            vendor_payout: Vendor's payout amount
            scheduled_pickup_date: Scheduled pickup datetime
        """
        # Get vendor with user info
        result = await db.execute(
            select(Vendor).where(Vendor.id == vendor_id)
        )
        vendor = result.scalar_one_or_none()

        if not vendor or not vendor.user:
            print(f"Vendor {vendor_id} not found or has no user account")
            return

        # Format pickup date
        pickup_date_str = scheduled_pickup_date.strftime("%B %d, %Y at %I:%M %p")

        # Email content
        subject = f"New Order Received - #{order_number}"

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>New Order Notification</title>
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
                    line-height: 1.6;
                    color: #1E5053;
                    background-color: #f8f9fa;
                    margin: 0;
                    padding: 0;
                }}
                .container {{
                    max-width: 600px;
                    margin: 0 auto;
                    background-color: #ffffff;
                    padding: 0;
                }}
                .header {{
                    background-color: #1E5053;
                    padding: 30px 40px;
                    text-align: center;
                }}
                .header h1 {{
                    color: #ffffff;
                    margin: 0;
                    font-size: 24px;
                    font-weight: 600;
                }}
                .content {{
                    padding: 40px;
                }}
                .greeting {{
                    font-size: 18px;
                    margin-bottom: 20px;
                    color: #1E5053;
                }}
                .order-box {{
                    background-color: #f8f9fa;
                    border-left: 4px solid #1E5053;
                    padding: 20px;
                    margin: 20px 0;
                }}
                .order-box h2 {{
                    color: #1E5053;
                    font-size: 16px;
                    margin-top: 0;
                    margin-bottom: 15px;
                }}
                .order-details {{
                    margin: 15px 0;
                }}
                .detail-row {{
                    display: flex;
                    justify-content: space-between;
                    padding: 8px 0;
                    border-bottom: 1px solid #e9ecef;
                }}
                .detail-label {{
                    font-weight: 600;
                    color: #1E5053;
                }}
                .detail-value {{
                    color: #495057;
                }}
                .pickup-info {{
                    background-color: #e7f3f4;
                    padding: 15px;
                    border-radius: 4px;
                    margin: 20px 0;
                }}
                .pickup-info strong {{
                    color: #1E5053;
                }}
                .action-button {{
                    display: inline-block;
                    background-color: #1E5053;
                    color: #ffffff !important;
                    text-decoration: none;
                    padding: 12px 30px;
                    border-radius: 4px;
                    margin: 20px 0;
                    font-weight: 600;
                }}
                .footer {{
                    background-color: #f8f9fa;
                    padding: 30px 40px;
                    text-align: center;
                    font-size: 12px;
                    color: #6c757d;
                }}
                .footer a {{
                    color: #1E5053;
                    text-decoration: none;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🎉 New Order Received!</h1>
                </div>

                <div class="content">
                    <p class="greeting">Hello {vendor.business_name},</p>

                    <p>Great news! You've received a new order on SHOPSOMA.</p>

                    <div class="order-box">
                        <h2>Order Details</h2>
                        <div class="order-details">
                            <div class="detail-row">
                                <span class="detail-label">Order Number:</span>
                                <span class="detail-value">#{order_number}</span>
                            </div>
                            <div class="detail-row">
                                <span class="detail-label">Product:</span>
                                <span class="detail-value">{product_title}</span>
                            </div>
                            <div class="detail-row">
                                <span class="detail-label">Quantity:</span>
                                <span class="detail-value">{quantity}</span>
                            </div>
                            <div class="detail-row">
                                <span class="detail-label">Your Payout:</span>
                                <span class="detail-value">₦{vendor_payout:,.2f}</span>
                            </div>
                        </div>
                    </div>

                    <div class="pickup-info">
                        <strong>📦 Pickup Scheduled:</strong><br>
                        Our logistics partner will pick up your order on <strong>{pickup_date_str}</strong>.
                        <br><br>
                        Please ensure the product is ready for pickup at the scheduled time.
                    </div>

                    <p>
                        <a href="https://vendor.shopsoma.com/dashboard" class="action-button">
                            View Order in Dashboard
                        </a>
                    </p>

                    <p style="margin-top: 30px; color: #6c757d; font-size: 14px;">
                        <strong>Next Steps:</strong><br>
                        1. Prepare the order according to customer specifications<br>
                        2. Package the item securely<br>
                        3. Ensure it's ready for pickup at the scheduled time<br>
                        4. Our logistics partner will handle the rest
                    </p>

                    <p style="margin-top: 20px; color: #6c757d; font-size: 14px;">
                        Need help? Contact our seller support at
                        <a href="mailto:partnerships@shopsoma.com" style="color: #1E5053;">partnerships@shopsoma.com</a>
                    </p>
                </div>

                <div class="footer">
                    <p>© {datetime.utcnow().year} SHOPSOMA. All rights reserved.</p>
                    <p>
                        <a href="https://shopsoma.com">Visit SHOPSOMA</a> |
                        <a href="https://vendor.shopsoma.com">Vendor Dashboard</a> |
                        <a href="mailto:partnerships@shopsoma.com">Support</a>
                    </p>
                </div>
            </div>
        </body>
        </html>
        """

        # Plain text version
        text_content = f"""
        New Order Received!

        Hello {vendor.business_name},

        You've received a new order on SHOPSOMA:

        Order Number: #{order_number}
        Product: {product_title}
        Quantity: {quantity}
        Your Payout: ₦{vendor_payout:,.2f}

        Pickup Scheduled: {pickup_date_str}

        Our logistics partner will pick up your order at the scheduled time.
        Please ensure the product is ready for pickup.

        View your order: https://vendor.shopsoma.com/dashboard

        Need help? Contact: partnerships@shopsoma.com

        © {datetime.utcnow().year} SHOPSOMA
        """

        try:
            await self.email_service.send_email(
                to_email=vendor.user.email,
                subject=subject,
                html_content=html_content,
                text_content=text_content
            )

            # Update notification email_sent status
            notification_result = await db.execute(
                select(VendorNotification).where(
                    VendorNotification.vendor_id == vendor_id,
                    VendorNotification.order_id.isnot(None)
                ).order_by(VendorNotification.created_at.desc()).limit(1)
            )
            notification = notification_result.scalar_one_or_none()

            if notification:
                notification.email_sent = True
                notification.email_sent_at = datetime.utcnow()
                await db.commit()

            print(f"✅ Order notification email sent to vendor {vendor.business_name}")

        except Exception as e:
            print(f"❌ Failed to send order notification email to vendor {vendor.business_name}: {e}")

    async def send_pickup_reminder(
        self,
        db: AsyncSession,
        vendor_id: str,
        order_number: str,
        pickup_date: datetime,
        pickup_address: str
    ):
        """
        Send pickup reminder to vendor (24 hours before pickup)

        Args:
            db: Database session
            vendor_id: Vendor ID
            order_number: Order number
            pickup_date: Pickup datetime
            pickup_address: Pickup address
        """
        # Get vendor
        result = await db.execute(
            select(Vendor).where(Vendor.id == vendor_id)
        )
        vendor = result.scalar_one_or_none()

        if not vendor or not vendor.user:
            return

        subject = f"Pickup Reminder - Order #{order_number}"
        pickup_date_str = pickup_date.strftime("%B %d, %Y at %I:%M %p")

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: Arial, sans-serif; color: #1E5053; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background-color: #1E5053; color: white; padding: 20px; text-align: center; }}
                .content {{ padding: 30px; background-color: #f8f9fa; }}
                .reminder-box {{ background-color: #fff3cd; padding: 15px; border-left: 4px solid #ffc107; margin: 20px 0; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>⏰ Pickup Reminder</h1>
                </div>
                <div class="content">
                    <p>Hello {vendor.business_name},</p>

                    <div class="reminder-box">
                        <strong>Your order pickup is scheduled for tomorrow:</strong><br><br>
                        <strong>Order:</strong> #{order_number}<br>
                        <strong>Pickup Time:</strong> {pickup_date_str}<br>
                        <strong>Pickup Address:</strong> {pickup_address}
                    </div>

                    <p>Please ensure your order is:</p>
                    <ul>
                        <li>Properly packaged and labeled</li>
                        <li>Ready at the pickup address</li>
                        <li>Matches customer specifications</li>
                    </ul>

                    <p>Contact: partnerships@shopsoma.com</p>
                </div>
            </div>
        </body>
        </html>
        """

        try:
            await self.email_service.send_email(
                to_email=vendor.user.email,
                subject=subject,
                html_content=html_content
            )
            print(f"✅ Pickup reminder sent to vendor {vendor.business_name}")
        except Exception as e:
            print(f"❌ Failed to send pickup reminder: {e}")

    async def send_payout_notification(
        self,
        db: AsyncSession,
        vendor_id: str,
        payout_amount: float,
        period_start: datetime,
        period_end: datetime,
        total_orders: int
    ):
        """
        Send monthly payout notification to vendor

        Args:
            db: Database session
            vendor_id: Vendor ID
            payout_amount: Payout amount
            period_start: Payout period start date
            period_end: Payout period end date
            total_orders: Total number of orders in period
        """
        # Get vendor
        result = await db.execute(
            select(Vendor).where(Vendor.id == vendor_id)
        )
        vendor = result.scalar_one_or_none()

        if not vendor or not vendor.user:
            return

        period_str = f"{period_start.strftime('%B %d')} - {period_end.strftime('%B %d, %Y')}"
        subject = f"Your SHOPSOMA Payout is Ready - ₦{payout_amount:,.2f}"

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: Arial, sans-serif; color: #1E5053; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background-color: #1E5053; color: white; padding: 20px; text-align: center; }}
                .content {{ padding: 30px; background-color: #ffffff; }}
                .payout-box {{ background-color: #d4edda; padding: 20px; border-left: 4px solid #28a745; margin: 20px 0; text-align: center; }}
                .amount {{ font-size: 32px; font-weight: bold; color: #28a745; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>💰 Payout Processed!</h1>
                </div>
                <div class="content">
                    <p>Hello {vendor.business_name},</p>

                    <p>Your payout for the period {period_str} has been processed.</p>

                    <div class="payout-box">
                        <p>Payout Amount</p>
                        <div class="amount">₦{payout_amount:,.2f}</div>
                        <p style="margin-top: 10px; color: #6c757d;">Based on {total_orders} completed orders</p>
                    </div>

                    <p>The funds will be transferred to your registered bank account within 3-5 business days.</p>

                    <p><strong>Bank Details on File:</strong><br>
                    {vendor.bank_name or 'Not provided'}<br>
                    {vendor.bank_account_number or 'Not provided'}</p>

                    <p style="margin-top: 30px;">
                        <a href="https://vendor.shopsoma.com/payouts" style="background-color: #1E5053; color: white; padding: 12px 24px; text-decoration: none; border-radius: 4px;">
                            View Payout Details
                        </a>
                    </p>

                    <p style="margin-top: 20px; color: #6c757d; font-size: 14px;">
                        Questions about your payout? Contact: partnerships@shopsoma.com
                    </p>
                </div>
            </div>
        </body>
        </html>
        """

        try:
            await self.email_service.send_email(
                to_email=vendor.user.email,
                subject=subject,
                html_content=html_content
            )

            # Create notification record
            notification = VendorNotification(
                vendor_id=vendor_id,
                notification_type="payout_processed",
                title=f"Payout Processed - ₦{payout_amount:,.2f}",
                message=f"Your payout for {period_str} has been processed and will arrive in 3-5 business days.",
                data={
                    "payout_amount": payout_amount,
                    "period_start": period_start.isoformat(),
                    "period_end": period_end.isoformat(),
                    "total_orders": total_orders
                },
                email_sent=True,
                email_sent_at=datetime.utcnow()
            )
            db.add(notification)
            await db.commit()

            print(f"✅ Payout notification sent to vendor {vendor.business_name}")
        except Exception as e:
            print(f"❌ Failed to send payout notification: {e}")
