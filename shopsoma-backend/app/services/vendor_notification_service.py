"""Vendor notification email service"""
from datetime import datetime
from typing import List, Dict, Any
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models import Vendor, VendorNotification
from app.services.email_service import EmailService

logger = logging.getLogger(__name__)

class VendorNotificationService:
    """Service for sending vendor notifications via email"""

    def __init__(self, email_service: EmailService):
        self.email_service = email_service

    async def send_order_notification(
        self,
        db: AsyncSession,
        vendor_id: str,
        order_id: str,
        order_number: str,
        order_date: datetime,
        items: List[Dict[str, Any]],
        total_payout: float,
        scheduled_pickup_date: datetime,
        currency: str = "NGN",
    ):
        """
        Send order placed notification to vendor

        Args:
            db: Database session
            vendor_id: Vendor ID
            order_id: Order ID
            order_number: Order number
            order_date: Order created datetime
            items: List of order items for this vendor
            total_payout: Total payout for this vendor
            scheduled_pickup_date: Scheduled pickup datetime
        """
        # Get vendor with user info
        result = await db.execute(
            select(Vendor).options(selectinload(Vendor.user)).where(Vendor.id == vendor_id)
        )
        vendor = result.scalar_one_or_none()

        if not vendor or not vendor.user:
            logger.warning("[Vendor Email] Vendor not found or missing user for vendor_id=%s", vendor_id)
            return
        if not vendor.user.email:
            logger.warning("[Vendor Email] Vendor missing email for vendor_id=%s", vendor_id)
            return

        try:
            await self.email_service.send_vendor_new_order_email(
                email=vendor.user.email,
                name=vendor.business_name,
                order_number=order_number,
                order_date=order_date,
                items=items,
                total_payout=total_payout,
                pickup_date=scheduled_pickup_date,
                currency=currency,
            )

            # Update notification email_sent status
            notification_result = await db.execute(
                select(VendorNotification).where(
                    VendorNotification.vendor_id == vendor_id,
                    VendorNotification.order_id == order_id,
                    VendorNotification.notification_type == "order_placed"
                ).order_by(VendorNotification.created_at.desc()).limit(1)
            )
            notification = notification_result.scalar_one_or_none()

            if notification:
                notification.email_sent = True
                notification.email_sent_at = datetime.utcnow()
                await db.commit()

            logger.info(
                "[Vendor Email] New order email sent to vendor_id=%s order=%s",
                vendor_id,
                order_number
            )

        except Exception as e:
            logger.exception(
                "[Vendor Email] Failed to send vendor email for vendor_id=%s order=%s: %s",
                vendor_id,
                order_number,
                e
            )

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
            logger.info(
                "[Vendor Email] Pickup reminder sent to vendor_id=%s order=%s",
                vendor_id,
                order_number
            )
        except Exception as e:
            logger.exception(
                "[Vendor Email] Failed to send pickup reminder for vendor_id=%s order=%s: %s",
                vendor_id,
                order_number,
                e
            )

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

            logger.info("[Vendor Email] Payout notification sent to vendor_id=%s", vendor_id)
        except Exception as e:
            logger.exception(
                "[Vendor Email] Failed to send payout notification for vendor_id=%s: %s",
                vendor_id,
                e
            )
