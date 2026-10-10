"""Order notification service for vendor and customer emails"""
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from datetime import datetime
import logging

from app.models.order import Order, OrderItem, FulfillmentStatus, PaymentStatus
from app.models.user import User
from app.models.vendor import Vendor
from app.models.vendor_pickup import VendorNotification
from app.services.email_service import EmailService

# Set up logger
logger = logging.getLogger(__name__)


# Status message mappings for different audiences
VENDOR_STATUS_MESSAGES = {
    FulfillmentStatus.ORDER_RECEIVED: {
        "title": "New Order Received",
        "message": "A new order has been placed. Please begin preparing items for pickup.",
        "action_required": True,
        "send_email": True,
    },
    FulfillmentStatus.PREPARING_FOR_PICKUP: {
        "title": "Pack Order - Awaiting Rider",
        "message": "Please pack the order items. A pickup will be scheduled soon.",
        "action_required": True,
        "send_email": True,
    },
    FulfillmentStatus.PICKUP_SCHEDULED: {
        "title": "Pickup Scheduled",
        "message": "Pickup has been scheduled. Please have items ready during the pickup window.",
        "action_required": True,
        "send_email": True,
    },
    FulfillmentStatus.PICKED_UP: {
        "title": "Items Picked Up",
        "message": "Your items have been handed over to the courier successfully.",
        "action_required": False,
        "send_email": True,
    },
    FulfillmentStatus.IN_TRANSIT: {
        "title": "On the Way to Customer",
        "message": "Items are in transit to the customer.",
        "action_required": False,
        "send_email": False,
    },
    FulfillmentStatus.OUT_FOR_DELIVERY: {
        "title": "Out for Delivery",
        "message": "Items are out for delivery to the customer.",
        "action_required": False,
        "send_email": False,
    },
    FulfillmentStatus.DELIVERED: {
        "title": "Order Delivered Successfully",
        "message": "The order has been delivered to the customer. Payment will be processed soon.",
        "action_required": False,
        "send_email": True,
    },
    FulfillmentStatus.DELIVERY_FAILED: {
        "title": "Delivery Failed",
        "message": "Delivery attempt failed. Our logistics team will retry delivery.",
        "action_required": False,
        "send_email": True,
    },
    FulfillmentStatus.RETURNED: {
        "title": "Order Returned",
        "message": "The order has been returned. Please contact support for details.",
        "action_required": True,
        "send_email": True,
    },
    FulfillmentStatus.CANCELLED: {
        "title": "Order Cancelled",
        "message": "This order has been cancelled.",
        "action_required": False,
        "send_email": True,
    },
}

CUSTOMER_STATUS_MESSAGES = {
    FulfillmentStatus.ORDER_RECEIVED: {
        "title": "Order Confirmed",
        "message": "Your order has been confirmed and is being processed.",
        "send_email": False,
    },
    FulfillmentStatus.PREPARING_FOR_PICKUP: {
        "title": "Order Being Prepared",
        "message": "Your order is being prepared by the vendor.",
        "send_email": False,
    },
    FulfillmentStatus.PICKUP_SCHEDULED: {
        "title": "Pickup Arranged",
        "message": "Pickup from vendor has been arranged. Your order will be dispatched soon.",
        "send_email": False,
    },
    FulfillmentStatus.PICKED_UP: {
        "title": "Order Dispatched",
        "message": "Your order has been dispatched and is on its way to you.",
        "send_email": False,
    },
    FulfillmentStatus.IN_TRANSIT: {
        "title": "In Transit",
        "message": "Your order is in transit and will arrive soon.",
        "send_email": False,
    },
    FulfillmentStatus.OUT_FOR_DELIVERY: {
        "title": "Out for Delivery",
        "message": "Your order is out for delivery and will arrive today.",
        "send_email": True,
    },
    FulfillmentStatus.DELIVERED: {
        "title": "Delivered Successfully",
        "message": "Your order has been delivered. Thank you for shopping with us!",
        "send_email": True,
    },
    FulfillmentStatus.DELIVERY_FAILED: {
        "title": "Delivery Attempt Failed",
        "message": "We couldn't deliver your order. We'll try again soon or contact you.",
        "send_email": True,
    },
    FulfillmentStatus.RETURNED: {
        "title": "Order Returned",
        "message": "Your order has been returned. A refund will be processed.",
        "send_email": True,
    },
    FulfillmentStatus.CANCELLED: {
        "title": "Order Cancelled",
        "message": "Your order has been cancelled. A refund will be processed if payment was made.",
        "send_email": True,
    },
}


class OrderNotificationService:
    """Service for handling order status change notifications"""

    def __init__(self, db: AsyncSession, email_service: Optional[EmailService] = None):
        self.db = db
        self.email_service = email_service or EmailService()

    async def notify_status_change(
        self,
        order: Order,
        new_status: FulfillmentStatus,
        pickup_details: Optional[Dict[str, Any]] = None
    ) -> Dict[str, bool]:
        """
        Send notifications to vendor and customer on status change

        Args:
            order: Order object
            new_status: New fulfillment status
            pickup_details: Optional dict with pickup window info

        Returns:
            Dict with vendor_notified and customer_notified boolean flags
        """
        logger.info(f"📢 notify_status_change called for order {order.order_number}: status={new_status.value}")

        result = {
            "vendor_notified": False,
            "customer_notified": False,
        }

        # Notify vendors
        logger.info(f"👔 Attempting to notify vendors for order {order.order_number}")
        vendor_notified = await self._notify_vendors(order, new_status, pickup_details)
        result["vendor_notified"] = vendor_notified
        logger.info(f"👔 Vendor notification result: {vendor_notified}")

        # Notify customer
        logger.info(f"👤 Attempting to notify customer for order {order.order_number}")
        customer_notified = await self._notify_customer(order, new_status, pickup_details)
        result["customer_notified"] = customer_notified
        logger.info(f"👤 Customer notification result: {customer_notified}")

        logger.info(f"📊 Notification summary for order {order.order_number}: vendor={vendor_notified}, customer={customer_notified}")

        return result

    async def _notify_vendors(
        self,
        order: Order,
        new_status: FulfillmentStatus,
        pickup_details: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Send notification to all vendors involved in the order"""
        if isinstance(new_status, str):
            try:
                new_status = FulfillmentStatus(new_status)
            except ValueError:
                pass

        # Only notify vendors if the order is confirmed paid
        payment_status = getattr(order, "payment_status", None)
        if payment_status != PaymentStatus.PAID and payment_status != "paid":
            logger.warning(
                f"[Vendor Email] Suppressing vendor notification for order {order.order_number}: payment status is {payment_status} (not paid)"
            )
            return False

        status_config = VENDOR_STATUS_MESSAGES.get(new_status)
        if not status_config or not status_config["send_email"]:
            return False

        # Get all unique vendors for this order
        vendor_ids = {item.vendor_id for item in order.items}

        notifications_sent = 0
        for vendor_id in vendor_ids:
            try:
                # Load vendor with user
                vendor_query = select(Vendor).options(selectinload(Vendor.user)).where(Vendor.id == vendor_id)
                vendor_result = await self.db.execute(vendor_query)
                vendor = vendor_result.scalar_one_or_none()

                if not vendor or not vendor.user or not vendor.user.email:
                    continue

                # Build email content
                email_content = self._build_vendor_email(
                    vendor=vendor,
                    order=order,
                    status_config=status_config,
                    pickup_details=pickup_details
                )

                # Send email
                await self.email_service.send_email(
                    to_email=vendor.user.email,
                    to_name=vendor.business_name,
                    subject=f"Order {order.order_number}: {status_config['title']}",
                    html_content=email_content
                )

                # Create in-app notification
                await self._create_vendor_notification(
                    vendor_id=vendor_id,
                    order=order,
                    status_config=status_config,
                    pickup_details=pickup_details
                )

                notifications_sent += 1

            except Exception as e:
                # Log error but continue with other vendors
                print(f"Failed to notify vendor {vendor_id}: {str(e)}")
                continue

        return notifications_sent > 0

    async def notify_vendor_item_pickup_scheduled(
        self,
        order: Order,
        vendor: Vendor,
        item: OrderItem,
        pickup: Any,
    ) -> bool:
        """Send notification to a specific vendor when pickup is scheduled for their individual item."""
        payment_status = getattr(order, "payment_status", None)
        if payment_status != PaymentStatus.PAID and payment_status != "paid":
            logger.warning(
                f"[Vendor Email] Suppressing vendor pickup notification for order {order.order_number}: payment status is {payment_status}"
            )
            return False

        if not vendor or not getattr(vendor, "user", None) or not getattr(vendor.user, "email", None):
            logger.warning(f"[Vendor Email] Vendor or vendor user email missing for vendor {getattr(vendor, 'id', None)}")
            return False

        pickup_details = {
            "pickup_window_start": getattr(pickup, "pickup_window_start", None),
            "pickup_window_end": getattr(pickup, "pickup_window_end", None),
            "courier_name": getattr(pickup, "courier_name", None),
            "rider_id": getattr(pickup, "rider_id", None),
            "scheduled_pickup_date": getattr(pickup, "scheduled_pickup_date", None),
        }

        pickup_window_info = ""
        if pickup_details.get("scheduled_pickup_date"):
            sched = pickup_details["scheduled_pickup_date"]
            sched_str = sched.strftime('%B %d, %Y · %I:%M %p') if hasattr(sched, 'strftime') else str(sched)
            pickup_window_info += f"""
            <div style="margin:16px 0;padding:12px;background:#F3F4F6;border-radius:8px;">
                <p style="margin:0;color:#6B7280;font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:0.05em;">Pickup Scheduled</p>
                <p style="margin:4px 0 0;color:#111827;font-size:14px;font-weight:500;">{sched_str}</p>
            </div>
            """
        if pickup_details.get("pickup_window_start") and pickup_details.get("pickup_window_end"):
            start = pickup_details["pickup_window_start"]
            end = pickup_details["pickup_window_end"]
            start_str = start.strftime('%B %d, %Y %I:%M %p') if hasattr(start, 'strftime') else str(start)
            end_str = end.strftime('%I:%M %p') if hasattr(end, 'strftime') else str(end)
            pickup_window_info += f"""
            <div style="margin:16px 0;padding:12px;background:#F3F4F6;border-radius:8px;">
                <p style="margin:0;color:#6B7280;font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:0.05em;">Pickup Window</p>
                <p style="margin:4px 0 0;color:#111827;font-size:14px;font-weight:500;">{start_str} - {end_str}</p>
            </div>
            """
        if pickup_details.get("courier_name"):
            courier_line = pickup_details['courier_name']
            if pickup_details.get("rider_id"):
                courier_line += f" (Rider: {pickup_details['rider_id']})"
            pickup_window_info += f"""
            <div style="margin:8px 0;padding:12px;background:#F3F4F6;border-radius:8px;">
                <p style="margin:0;color:#6B7280;font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:0.05em;">Courier / Rider</p>
                <p style="margin:4px 0 0;color:#111827;font-size:14px;font-weight:500;">{courier_line}</p>
            </div>
            """

        variant_summary = ""
        if hasattr(item, "variant_details") and item.variant_details:
            parts = [f"{k}: {v}" for k, v in item.variant_details.items() if v]
            if parts:
                variant_summary = f"<p style='margin:2px 0 0;color:#6B7280;font-size:12px;'>{' · '.join(parts)}</p>"

        item_html = f"""
        <div style="padding:12px 0;border-bottom:1px solid #E5E7EB;">
            <p style="margin:0;color:#111827;font-size:14px;font-weight:500;">{item.product_title}</p>
            <p style="margin:4px 0 0;color:#6B7280;font-size:13px;">Quantity: {item.quantity}</p>
            {variant_summary}
        </div>
        """

        action_required_html = """
        <div style="margin:24px 0;padding:16px;background:#FEF3C7;border-left:4px solid #F59E0B;border-radius:4px;">
            <p style="margin:0;color:#92400E;font-size:14px;font-weight:600;">⚠️ Action Required</p>
            <p style="margin:4px 0 0;color:#92400E;font-size:13px;">Please have this item packaged and ready for collection during the pickup window.</p>
        </div>
        """

        body_content = f"""
        <p style="margin:0 0 24px;color:#111827;font-size:14px;line-height:1.6;">Hello {vendor.business_name},</p>
        <p style="margin:0 0 24px;color:#4B5563;font-size:14px;line-height:1.6;">Pickup has been scheduled for your item from order #{order.order_number}. Please have the item ready during the pickup window.</p>

        <div style="margin:24px 0;">
            <h2 style="margin:0 0 16px;color:#111827;font-size:16px;font-weight:600;text-transform:uppercase;letter-spacing:0.05em;">Order Details</h2>
            <div style="background:#F9FAFB;padding:16px;border-radius:8px;margin-bottom:8px;">
                <p style="margin:0;color:#6B7280;font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:0.05em;">Order Number</p>
                <p style="margin:4px 0 0;color:#111827;font-size:16px;font-weight:600;">{order.order_number}</p>
            </div>
        </div>

        {pickup_window_info}

        <div style="margin:24px 0;">
            <h2 style="margin:0 0 16px;color:#111827;font-size:16px;font-weight:600;text-transform:uppercase;letter-spacing:0.05em;">Scheduled Item</h2>
            <div style="background:#FFFFFF;border:1px solid #E5E7EB;border-radius:8px;padding:8px 16px;">
                {item_html}
            </div>
        </div>

        {action_required_html}

        <p style="margin:24px 0 0;color:#6B7280;font-size:13px;line-height:1.6;">Thank you for being a valued partner!</p>
        <p style="margin:4px 0 0;color:#6B7280;font-size:13px;font-weight:600;">Shopsoma Team</p>
        """

        subject = f"Order {order.order_number}: Pickup Scheduled for {item.product_title}"
        html_content = self.email_service._wrap_email(
            heading="Pickup Scheduled",
            body_html=body_content,
            preheader=f"Order {order.order_number}: Pickup scheduled for {item.product_title}"
        )

        try:
            await self.email_service.send_email(
                to_email=vendor.user.email,
                to_name=vendor.business_name,
                subject=subject,
                html_content=html_content,
            )
            logger.info(f"📧 Sent item pickup notification to vendor {vendor.business_name} ({vendor.user.email}) for item {item.product_title}")
        except Exception as e:
            logger.error(f"Failed to send email to vendor {vendor.business_name}: {e}")

        # In-app notification
        try:
            notification = VendorNotification(
                vendor_id=vendor.id,
                notification_type="item_pickup_scheduled",
                title=f"Pickup Scheduled: {item.product_title}",
                message=f"Pickup has been scheduled for {item.product_title} ({order.order_number}).",
                order_id=order.id,
                data={
                    "order_number": order.order_number,
                    "order_id": str(order.id),
                    "order_item_id": str(item.id),
                    "product_title": item.product_title,
                    "pickup_details": {
                        k: (v.isoformat() if isinstance(v, datetime) else v)
                        for k, v in pickup_details.items()
                        if v is not None
                    },
                },
                email_sent=True,
                email_sent_at=datetime.utcnow(),
            )
            self.db.add(notification)
            await self.db.commit()
        except Exception as e:
            logger.error(f"Failed to create in-app notification for vendor {vendor.id}: {e}")

        return True

    async def _notify_customer(
        self,
        order: Order,
        new_status: FulfillmentStatus,
        pickup_details: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Send notification to customer"""
        if isinstance(new_status, str):
            try:
                new_status = FulfillmentStatus(new_status)
            except ValueError:
                pass

        status_val = getattr(new_status, "value", str(new_status))
        logger.info(f"🔔 _notify_customer called for order {order.order_number}, status: {status_val}")

        status_config = CUSTOMER_STATUS_MESSAGES.get(new_status)
        if not status_config:
            logger.warning(f"❌ No status config found for status: {status_val}")
            return False

        if not status_config["send_email"]:
            logger.info(f"⏭️  Customer email sending disabled for status: {status_val}")
            return False

        logger.info(f"✅ Customer email enabled for status: {new_status.value} - '{status_config['title']}'")

        try:
            # Load customer
            customer = order.customer
            if not customer:
                logger.error(f"❌ No customer found for order {order.order_number}")
                return False

            if not customer.email:
                logger.error(f"❌ Customer {customer.id} has no email for order {order.order_number}")
                return False

            logger.info(f"📧 Preparing to send customer email to: {customer.email}")

            # Build email content
            email_content = self._build_customer_email(
                customer=customer,
                order=order,
                status_config=status_config,
                pickup_details=pickup_details
            )

            logger.info(f"📝 Email content built, length: {len(email_content)} chars")

            # Send email
            customer_name = customer.full_name if customer.full_name else customer.email
            logger.info(f"🚀 Calling email service to send to {customer.email} (name: {customer_name})")

            email_sent = await self.email_service.send_email(
                to_email=customer.email,
                to_name=customer_name,
                subject=f"Order {order.order_number}: {status_config['title']}",
                html_content=email_content
            )

            if email_sent:
                logger.info(f"✅ Customer email sent successfully to {customer.email}")
            else:
                logger.warning(f"⚠️  Email service returned False for {customer.email}")

            return email_sent

        except Exception as e:
            logger.error(f"❌ Failed to notify customer for order {order.id}: {str(e)}", exc_info=True)
            return False

    def _build_vendor_email(
        self,
        vendor: Vendor,
        order: Order,
        status_config: Dict[str, Any],
        pickup_details: Optional[Dict[str, Any]] = None
    ) -> str:
        """Build vendor email content with branded HTML template"""

        pickup_window_info = ""
        if pickup_details:
            if pickup_details.get("scheduled_pickup_date"):
                sched = pickup_details["scheduled_pickup_date"]
                sched_str = sched.strftime('%B %d, %Y · %I:%M %p') if hasattr(sched, 'strftime') else str(sched)
                pickup_window_info += f"""
                <div style="margin:16px 0;padding:12px;background:#F3F4F6;border-radius:8px;">
                    <p style="margin:0;color:#6B7280;font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:0.05em;">Pickup Scheduled</p>
                    <p style="margin:4px 0 0;color:#111827;font-size:14px;font-weight:500;">{sched_str}</p>
                </div>
                """
            if pickup_details.get("pickup_window_start") and pickup_details.get("pickup_window_end"):
                start = pickup_details["pickup_window_start"]
                end = pickup_details["pickup_window_end"]
                start_str = start.strftime('%B %d, %Y %I:%M %p') if hasattr(start, 'strftime') else str(start)
                end_str = end.strftime('%I:%M %p') if hasattr(end, 'strftime') else str(end)
                pickup_window_info += f"""
                <div style="margin:16px 0;padding:12px;background:#F3F4F6;border-radius:8px;">
                    <p style="margin:0;color:#6B7280;font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:0.05em;">Pickup Window</p>
                    <p style="margin:4px 0 0;color:#111827;font-size:14px;font-weight:500;">{start_str} - {end_str}</p>
                </div>
                """
            if pickup_details.get("courier_name"):
                pickup_window_info += f"""
                <div style="margin:8px 0;padding:12px;background:#F3F4F6;border-radius:8px;">
                    <p style="margin:0;color:#6B7280;font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:0.05em;">Courier</p>
                    <p style="margin:4px 0 0;color:#111827;font-size:14px;font-weight:500;">{pickup_details['courier_name']}</p>
                </div>
                """

        # Get vendor's items from this order
        vendor_items = [item for item in order.items if item.vendor_id == vendor.id]
        items_html = ""
        for item in vendor_items:
            items_html += f"""
            <div style="padding:12px 0;border-bottom:1px solid #E5E7EB;">
                <p style="margin:0;color:#111827;font-size:14px;font-weight:500;">{item.product_title}</p>
                <p style="margin:4px 0 0;color:#6B7280;font-size:13px;">Quantity: {item.quantity}</p>
            </div>
            """

        action_required_html = ""
        if status_config.get("action_required"):
            action_required_html = f"""
            <div style="margin:24px 0;padding:16px;background:#FEF3C7;border-left:4px solid #F59E0B;border-radius:4px;">
                <p style="margin:0;color:#92400E;font-size:14px;font-weight:600;">⚠️ Action Required</p>
                <p style="margin:4px 0 0;color:#92400E;font-size:13px;">Please prepare these items for pickup.</p>
            </div>
            """

        body_content = f"""
        <p style="margin:0 0 24px;color:#111827;font-size:14px;line-height:1.6;">Hello {vendor.business_name},</p>
        <p style="margin:0 0 24px;color:#4B5563;font-size:14px;line-height:1.6;">{status_config['message']}</p>

        <div style="margin:24px 0;">
            <h2 style="margin:0 0 16px;color:#111827;font-size:16px;font-weight:600;text-transform:uppercase;letter-spacing:0.05em;">Order Details</h2>
            <div style="background:#F9FAFB;padding:16px;border-radius:8px;margin-bottom:8px;">
                <p style="margin:0;color:#6B7280;font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:0.05em;">Order Number</p>
                <p style="margin:4px 0 0;color:#111827;font-size:16px;font-weight:600;">{order.order_number}</p>
            </div>
            <div style="background:#F9FAFB;padding:16px;border-radius:8px;">
                <p style="margin:0;color:#6B7280;font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:0.05em;">Order Date</p>
                <p style="margin:4px 0 0;color:#111827;font-size:14px;">{order.created_at.strftime('%B %d, %Y')}</p>
            </div>
        </div>

        {pickup_window_info}

        <div style="margin:24px 0;">
            <h2 style="margin:0 0 16px;color:#111827;font-size:16px;font-weight:600;text-transform:uppercase;letter-spacing:0.05em;">Your Items</h2>
            <div style="background:#FFFFFF;border:1px solid #E5E7EB;border-radius:8px;padding:8px 16px;">
                {items_html}
            </div>
        </div>

        {action_required_html}

        <p style="margin:24px 0 0;color:#6B7280;font-size:13px;line-height:1.6;">Thank you for being a valued partner!</p>
        <p style="margin:4px 0 0;color:#6B7280;font-size:13px;font-weight:600;">Shopsoma Team</p>
        """

        # Wrap with branded template
        return self.email_service._wrap_email(
            heading=status_config['title'],
            body_html=body_content,
            preheader=f"Order {order.order_number}: {status_config['title']}"
        )

    def _build_customer_email(
        self,
        customer: User,
        order: Order,
        status_config: Dict[str, Any],
        pickup_details: Optional[Dict[str, Any]] = None
    ) -> str:
        """Build customer email content with branded HTML template"""

        # Get customer name
        customer_name = customer.full_name if customer.full_name else customer.email.split('@')[0].title()
        order_currency = getattr(order, "currency", None) or "NGN"

        tracking_info = ""
        if order.tracking_number:
            tracking_info = f"""
            <div style="margin:16px 0;padding:12px;background:#F3F4F6;border-radius:8px;">
                <p style="margin:0;color:#6B7280;font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:0.05em;">Tracking Number</p>
                <p style="margin:4px 0 0;color:#111827;font-size:14px;font-weight:500;">{order.tracking_number}</p>
                {f'<p style="margin:4px 0 0;color:#6B7280;font-size:13px;">Carrier: {order.delivery_provider}</p>' if order.delivery_provider else ''}
            </div>
            """

        estimated_delivery = ""
        if order.estimated_delivery_date:
            estimated_delivery = f"""
            <div style="margin:8px 0;padding:12px;background:#F3F4F6;border-radius:8px;">
                <p style="margin:0;color:#6B7280;font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:0.05em;">Estimated Delivery</p>
                <p style="margin:4px 0 0;color:#111827;font-size:14px;font-weight:500;">{order.estimated_delivery_date.strftime('%B %d, %Y')}</p>
            </div>
            """

        # Build items list for customer
        items_html = ""
        for item in order.items:
            item_subtotal = self.email_service._format_amount(item.subtotal, order_currency)
            items_html += f"""
            <div style="padding:12px 0;border-bottom:1px solid #E5E7EB;">
                <p style="margin:0;color:#111827;font-size:14px;font-weight:500;">{item.product_title}</p>
                <div style="display:flex;justify-content:space-between;margin-top:4px;">
                    <p style="margin:0;color:#6B7280;font-size:13px;">Qty: {item.quantity}</p>
                    <p style="margin:0;color:#111827;font-size:13px;font-weight:500;">{item_subtotal}</p>
                </div>
            </div>
            """

        order_total = self.email_service._format_amount(order.total_amount, order_currency)

        body_content = f"""
        <p style="margin:0 0 24px;color:#111827;font-size:14px;line-height:1.6;">Hello {customer_name},</p>
        <p style="margin:0 0 24px;color:#4B5563;font-size:14px;line-height:1.6;">{status_config['message']}</p>

        <div style="margin:24px 0;">
            <h2 style="margin:0 0 16px;color:#111827;font-size:16px;font-weight:600;text-transform:uppercase;letter-spacing:0.05em;">Order Details</h2>
            <div style="background:#F9FAFB;padding:16px;border-radius:8px;margin-bottom:8px;">
                <p style="margin:0;color:#6B7280;font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:0.05em;">Order Number</p>
                <p style="margin:4px 0 0;color:#111827;font-size:16px;font-weight:600;">{order.order_number}</p>
            </div>
            <div style="background:#F9FAFB;padding:16px;border-radius:8px;margin-bottom:8px;">
                <p style="margin:0;color:#6B7280;font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:0.05em;">Order Date</p>
                <p style="margin:4px 0 0;color:#111827;font-size:14px;">{order.created_at.strftime('%B %d, %Y')}</p>
            </div>
            <div style="background:#F9FAFB;padding:16px;border-radius:8px;">
                <p style="margin:0;color:#6B7280;font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:0.05em;">Total Amount</p>
                <p style="margin:4px 0 0;color:#111827;font-size:18px;font-weight:700;">{order_total}</p>
            </div>
        </div>

        {tracking_info}
        {estimated_delivery}

        <div style="margin:24px 0;">
            <h2 style="margin:0 0 16px;color:#111827;font-size:16px;font-weight:600;text-transform:uppercase;letter-spacing:0.05em;">Order Items</h2>
            <div style="background:#FFFFFF;border:1px solid #E5E7EB;border-radius:8px;padding:8px 16px;">
                {items_html}
            </div>
        </div>

        <div style="margin:24px 0;padding:16px;background:#F0FDF4;border-left:4px solid #10B981;border-radius:4px;">
            <p style="margin:0;color:#065F46;font-size:13px;">💚 You can track your order status anytime by logging into your account at shopsoma.com</p>
        </div>

        <p style="margin:24px 0 0;color:#6B7280;font-size:13px;line-height:1.6;">Thank you for shopping with Shopsoma!</p>
        <p style="margin:4px 0 0;color:#6B7280;font-size:13px;font-weight:600;">Shopsoma Team</p>
        """

        # Wrap with branded template
        return self.email_service._wrap_email(
            heading=status_config['title'],
            body_html=body_content,
            preheader=f"Order {order.order_number}: {status_config['title']}"
        )

    async def _create_vendor_notification(
        self,
        vendor_id: str,
        order: Order,
        status_config: Dict[str, Any],
        pickup_details: Optional[Dict[str, Any]] = None
    ) -> None:
        """Create in-app notification for vendor"""

        notification_data = {
            "order_number": order.order_number,
            "order_id": str(order.id),
            "status": order.fulfillment_status.value,
        }

        if pickup_details:
            serializable_pickup_details = {}
            for k, v in pickup_details.items():
                if isinstance(v, datetime):
                    serializable_pickup_details[k] = v.isoformat()
                else:
                    serializable_pickup_details[k] = v
            notification_data["pickup_details"] = serializable_pickup_details

        notification = VendorNotification(
            vendor_id=vendor_id,
            notification_type=f"order_{order.fulfillment_status.value}",
            title=status_config["title"],
            message=status_config["message"],
            order_id=order.id,
            data=notification_data,
            email_sent=True,
            email_sent_at=datetime.utcnow()
        )

        self.db.add(notification)
        await self.db.commit()


def get_vendor_status_label(status: FulfillmentStatus) -> str:
    """Get vendor-facing label for a status"""
    config = VENDOR_STATUS_MESSAGES.get(status)
    return config["title"] if config else status.value.replace("_", " ").title()


def get_customer_status_label(status: FulfillmentStatus) -> str:
    """Get customer-facing label for a status"""
    config = CUSTOMER_STATUS_MESSAGES.get(status)
    return config["title"] if config else status.value.replace("_", " ").title()


def get_vendor_status_message(status: FulfillmentStatus) -> str:
    """Get vendor-facing message for a status"""
    config = VENDOR_STATUS_MESSAGES.get(status)
    return config["message"] if config else ""


def get_customer_status_message(status: FulfillmentStatus) -> str:
    """Get customer-facing message for a status"""
    config = CUSTOMER_STATUS_MESSAGES.get(status)
    return config["message"] if config else ""
