"""
Email Service using Brevo (formerly SendinBlue)
Handles all transactional email sending for the platform
"""
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
from urllib.parse import urljoin
from pathlib import Path
import base64
from app.core.config import settings

logger = logging.getLogger(__name__)

# Safe import of Brevo SDK - allows app to start even if not installed
try:
    import brevo_python
    from brevo_python.rest import ApiException
    BREVO_AVAILABLE = True
except ImportError:
    brevo_python = None
    ApiException = Exception  # Fallback to base Exception
    BREVO_AVAILABLE = False
    logger.warning(
        "Brevo SDK (brevo_python) is not installed. Email sending is disabled. "
        "Install with: pip install brevo-python"
    )

BRAND_PRIMARY = "#105E53"
BRAND_DARK = "#454444"
BRAND_LIGHT = "#F8F9FA"
BRAND_BORDER = "#E8ECEF"
ASSET_DIR = Path(__file__).resolve().parent.parent / "static/email"


def _load_data_uri(filename: str, fallback: str) -> str:
    path = ASSET_DIR / filename
    try:
        data = base64.b64encode(path.read_bytes()).decode('ascii')
        return f"data:image/png;base64,{data}"
    except Exception:
        return fallback


LOGO_FALLBACK = _load_data_uri("shopsoma-logo.png", "")
PRODUCT_PLACEHOLDER = _load_data_uri(
    "product-placeholder.png",
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)


class EmailService:
    """Service for sending transactional emails via Brevo"""

    def __init__(self):
        """Initialize Brevo API client"""
        self.enabled = BREVO_AVAILABLE

        if not BREVO_AVAILABLE:
            logger.warning("EmailService initialized but Brevo SDK is not available - emails will not be sent")
            self.api_instance = None
            self.sender = None
        else:
            try:
                configuration = brevo_python.Configuration()
                configuration.api_key['api-key'] = settings.BREVO_API_KEY
                self.api_instance = brevo_python.TransactionalEmailsApi(brevo_python.ApiClient(configuration))
                sender_name = (
                    getattr(settings, "BREVO_SENDER_NAME", None)
                    or getattr(settings, "SMTP_FROM_NAME", None)
                    or "Shopsoma"
                )
                sender_email = (
                    getattr(settings, "BREVO_SENDER_EMAIL", None)
                    or getattr(settings, "SMTP_FROM_EMAIL", None)
                    or getattr(settings, "FROM_EMAIL", None)
                    or ""
                )
                self.sender = {
                    "name": sender_name,
                    "email": sender_email
                }
                logger.info("EmailService initialized successfully with Brevo SDK")
            except Exception as e:
                logger.error(f"Failed to initialize Brevo API client: {e}")
                self.enabled = False
                self.api_instance = None
                self.sender = None

        self.asset_base = getattr(settings, "CDN_BASE_URL", "") or getattr(settings, "FRONTEND_BASE_URL", "")
        raw_logo = getattr(settings, "BRAND_LOGO_URL", "") or ""
        if raw_logo and not raw_logo.startswith(("http://", "https://", "data:")):
            base = (getattr(settings, "FRONTEND_BASE_URL", "") or "").rstrip("/")
            if base:
                raw_logo = f"{base}/{raw_logo.lstrip('/')}"
        self.logo_url = self._resolve_image_url(raw_logo, LOGO_FALLBACK)
        self.product_placeholder = PRODUCT_PLACEHOLDER

    @staticmethod
    def _format_amount(amount: float) -> str:
        return f"₦{amount:,.2f}"

    def _resolve_image_url(self, source: Optional[str], fallback: str) -> str:
        """Resolve image URL with proper fallback handling for email clients"""
        if not source or not source.strip():
            return fallback

        source = source.strip()

        # Already a data URI or absolute URL
        if source.startswith("data:") or source.startswith("http://") or source.startswith("https://"):
            return source

        # Try to construct full URL from relative path
        if self.asset_base and self.asset_base.strip():
            try:
                full_url = urljoin(self.asset_base.rstrip('/') + '/', source.lstrip('/'))
                # Verify it looks like a valid URL
                if full_url.startswith("http"):
                    return full_url
            except Exception:
                pass

        # Fall back to placeholder if we can't construct a valid URL
        return fallback

    def _wrap_email(self, heading: str, body_html: str, preheader: str = "") -> str:
        preheader_html = ""
        if preheader:
            preheader_html = f"""
            <div style="display:none;font-size:1px;color:#fff;line-height:1px;max-height:0;max-width:0;opacity:0;overflow:hidden;">
                {preheader}
            </div>
            """

        # Use text-based logo if no valid image URL
        logo_html = ""
        if self.logo_url and (self.logo_url.startswith("http") or self.logo_url.startswith("data:")):
            logo_html = f'<img src="{self.logo_url}" alt="Shopsoma" style="height:40px;display:block;" />'
        else:
            # Fallback to text-based logo
            logo_html = f'<div style="font-family:\'Lao MN\',\'Times New Roman\',serif;font-size:24px;font-weight:600;letter-spacing:0.2em;color:{BRAND_PRIMARY};text-align:center;">SHOPSOMA</div>'

        return f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8" />
            <meta name="viewport" content="width=device-width, initial-scale=1.0" />
            <title>Shopsoma</title>
        </head>
        <body style="margin:0;background:#ffffff;font-family:'Montserrat','Helvetica Neue',Arial,sans-serif;color:{BRAND_DARK};">
            {preheader_html}
            <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#ffffff;">
                <tr>
                    <td align="center" style="padding:32px 16px;">
                        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:640px;">
                            <tr>
                                <td align="center" style="padding-bottom:24px;">
                                    {logo_html}
                                </td>
                            </tr>
                            <tr>
                                <td style="padding:32px;background:#ffffff;border:1px solid {BRAND_BORDER};border-radius:12px;">
                                    <h1 style="font-family:'Lao MN','Times New Roman',serif;font-size:20px;letter-spacing:0.3em;font-weight:normal;text-transform:uppercase;color:{BRAND_DARK};text-align:center;margin:0 0 24px;">
                                        {heading}
                                    </h1>
                                    {body_html}
                                </td>
                            </tr>
                            <tr>
                                <td style="text-align:center;padding:32px 16px;color:#9CA3AF;font-size:12px;">
                                    © {datetime.now().year} Shopsoma. All rights reserved.<br/>
                                    Curated African luxury fashion.
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>
            </table>
        </body>
        </html>
        """

    async def send_email(
        self,
        to_email: str,
        to_name: str,
        subject: str,
        html_content: str,
        template_params: Optional[Dict[str, Any]] = None
    ) -> bool:
        # Check if email service is enabled
        if not self.enabled or self.api_instance is None:
            logger.warning(
                f"Email send skipped (to: {to_email}, subject: '{subject}'): "
                f"Brevo enabled={self.enabled}, api_instance={'configured' if self.api_instance else 'None'}, "
                f"BREVO_API_KEY={'set' if settings.BREVO_API_KEY else 'NOT SET'}"
            )
            return False

        try:
            logger.info(f"Sending email to {to_email} (name: {to_name}), subject: '{subject}'")
            send_smtp_email = brevo_python.SendSmtpEmail(
                to=[{"email": to_email, "name": to_name}],
                sender=self.sender,
                subject=subject,
                html_content=html_content
            )

            api_response = self.api_instance.send_transac_email(send_smtp_email)
            logger.info(f"✅ Email sent successfully to {to_email}. Message ID: {api_response.message_id}")
            return True

        except ApiException as e:
            logger.error(f"❌ Brevo API error sending email to {to_email}: {e.status} - {e.reason}")
            logger.error(f"Full error: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Unexpected error sending email to {to_email}: {type(e).__name__} - {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    async def send_welcome_email(self, email: str, name: str) -> bool:
        subject = "Welcome to Shopsoma"
        body_html = f"""
        <p style="font-size:16px;">Hi {name or 'there'},</p>
        <p>Welcome to Shopsoma – the premium marketplace celebrating African luxury fashion.</p>
        <div style="background:{BRAND_LIGHT};padding:20px;border-radius:10px;border:1px solid {BRAND_BORDER};margin:24px 0;">
            <p style="margin:0 0 12px;font-weight:600;">Inside your account:</p>
            <ul style="padding-left:20px;margin:0;color:{BRAND_DARK};">
                <li>Curated drops from top designers</li>
                <li>Seamless checkout with Paystack & Stripe</li>
                <li>Track orders in real time</li>
            </ul>
        </div>
        <p style="text-align:center;margin:32px 0;">
            <a href="https://shopsoma.com" style="display:inline-block;padding:14px 28px;background:{BRAND_PRIMARY};color:#fff;border-radius:999px;text-decoration:none;font-weight:600;">Discover Collections</a>
        </p>
        <p>If you ever need assistance, our concierges are a reply away.</p>
        """
        html_content = self._wrap_email("Welcome", body_html, "Your curated Shopsoma experience begins now.")
        return await self.send_email(email, name, subject, html_content)

    def _build_items_table(self, items: List[dict]) -> str:
        rows = ""
        for item in items:
            image_url = item.get("image_url") or item.get("image") or item.get("thumbnail")
            image = self._resolve_image_url(image_url, self.product_placeholder)

            name = item.get('product_name') or item.get('product_title') or 'Product'
            variant_details = item.get('variant') or ''
            if not variant_details:
                details_dict = item.get('variant_details')
                if isinstance(details_dict, dict):
                    variant_details = " · ".join(f"{k}: {v}" for k, v in details_dict.items() if v)

            # Use a div with background color as placeholder if no real image
            image_cell = ""
            if image and image.startswith("http"):
                image_cell = f'<img src="{image}" alt="{name}" style="width:56px;height:56px;border-radius:6px;object-fit:cover;display:block;" />'
            else:
                # Text-based placeholder for products
                image_cell = f'<div style="width:56px;height:56px;border-radius:6px;background:{BRAND_LIGHT};display:flex;align-items:center;justify-content:center;border:1px solid {BRAND_BORDER};"><span style="color:{BRAND_PRIMARY};font-size:20px;font-weight:600;">📦</span></div>'

            rows += f"""
            <tr>
                <td style="padding:12px;border-bottom:1px solid {BRAND_BORDER};width:72px;">
                    {image_cell}
                </td>
                <td style="padding:12px;border-bottom:1px solid {BRAND_BORDER};">
                    <strong>{name}</strong><br/>
                    {"<span style='color:#6B7280;font-size:12px;'>" + variant_details + "</span>" if variant_details else ""}
                </td>
                <td style="padding:12px;border-bottom:1px solid {BRAND_BORDER};text-align:center;">{item.get('quantity',1)}</td>
                <td style="padding:12px;border-bottom:1px solid {BRAND_BORDER};text-align:right;">{self._format_amount(item.get('price',0))}</td>
                <td style="padding:12px;border-bottom:1px solid {BRAND_BORDER};text-align:right;">{self._format_amount(item.get('subtotal',0))}</td>
            </tr>
            """
        return rows

    def _build_vendor_items_table(self, items: List[dict]) -> str:
        rows = ""
        for item in items:
            name = item.get("product_title") or item.get("product_name") or "Product"
            quantity = item.get("quantity", 1)
            payout = self._format_amount(item.get("vendor_payout", 0))
            variant_details = ""
            details_dict = item.get("variant_details")
            if isinstance(details_dict, dict):
                detail_parts = []
                size_value = details_dict.get("size")
                color_value = details_dict.get("color")
                if size_value:
                    detail_parts.append(f"size: {size_value}")
                if color_value:
                    detail_parts.append(f"color: {color_value}")
                variant_details = " · ".join(detail_parts)
            elif isinstance(details_dict, str):
                variant_details = details_dict

            image_url = item.get("image_url") or item.get("image") or item.get("thumbnail")
            resolved_image = self._resolve_image_url(image_url, self.product_placeholder)
            if resolved_image and resolved_image.startswith("http"):
                image_cell = f'<img src="{resolved_image}" alt="{name}" style="width:56px;height:56px;border-radius:6px;object-fit:cover;display:block;" />'
            else:
                image_cell = f'<div style="width:56px;height:56px;border-radius:6px;background:{BRAND_LIGHT};display:flex;align-items:center;justify-content:center;border:1px solid {BRAND_BORDER};"><span style="color:{BRAND_PRIMARY};font-size:20px;font-weight:600;">📦</span></div>'

            item_cell = f"""
            <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                <tr>
                    <td style="width:72px;padding-right:12px;vertical-align:top;">
                        {image_cell}
                    </td>
                    <td style="vertical-align:top;">
                        <strong>{name}</strong><br/>
                        {"<span style='color:#6B7280;font-size:12px;'>" + variant_details + "</span>" if variant_details else ""}
                    </td>
                </tr>
            </table>
            """

            rows += f"""
            <tr>
                <td style="padding:12px;border-bottom:1px solid {BRAND_BORDER};">
                    {item_cell}
                </td>
                <td style="padding:12px;border-bottom:1px solid {BRAND_BORDER};text-align:center;">{quantity}</td>
                <td style="padding:12px;border-bottom:1px solid {BRAND_BORDER};text-align:right;">{payout}</td>
            </tr>
            """

        return rows

    async def send_order_confirmation_email(
        self,
        email: str,
        name: str,
        order_number: str,
        order_date: datetime,
        items: list,
        subtotal: float,
        shipping: float,
        tax: float,
        total: float,
        shipping_address: Dict[str, str]
    ) -> bool:
        subject = f"Order Confirmation · {order_number}"
        items_table = self._build_items_table(items)
        def _addr(key: str):
            return shipping_address.get(key) or shipping_address.get(key.replace('_', ''))

        address_lines = "<br/>".join(
            filter(
                None,
                [
                    shipping_address.get('full_name'),
                    _addr('address_line_1'),
                    _addr('address_line_2'),
                    f"{shipping_address.get('city', '')}, {shipping_address.get('state', '')} {shipping_address.get('postal_code', '')}",
                    shipping_address.get('country', 'Nigeria'),
                    f"Phone: {shipping_address.get('phone_number', '')}",
                ],
            )
        )

        body_html = f"""
        <p style="font-size:16px;">Hi {name or 'there'},</p>
        <p>Thank you for placing your order with Shopsoma. Our artisans and logistics partners are preparing your pieces.</p>
        <div style="margin:24px 0;padding:20px;border:1px solid {BRAND_BORDER};border-radius:10px;background:{BRAND_LIGHT};">
            <p style="margin:0;"><strong>Order Number:</strong> {order_number}</p>
            <p style="margin:4px 0;"><strong>Order Date:</strong> {order_date.strftime('%d %B %Y · %I:%M %p')}</p>
        </div>
        <table style="width:100%;border-collapse:collapse;margin-bottom:24px;">
            <thead>
                <tr style="background:{BRAND_LIGHT};text-transform:uppercase;font-size:12px;letter-spacing:0.15em;color:#6B7280;">
                    <th style="padding:12px;text-align:left;">Item</th>
                    <th style="padding:12px;text-align:center;">Qty</th>
                    <th style="padding:12px;text-align:right;">Price</th>
                    <th style="padding:12px;text-align:right;">Subtotal</th>
                </tr>
            </thead>
            <tbody>
                {items_table}
            </tbody>
        </table>
        <div style="border:1px solid {BRAND_BORDER};border-radius:10px;padding:20px;margin-bottom:24px;">
            <table style="width:100%;font-size:14px;">
                <tr><td>Subtotal</td><td style="text-align:right;">{self._format_amount(subtotal)}</td></tr>
                <tr><td>Shipping</td><td style="text-align:right;">{self._format_amount(shipping)}</td></tr>
                <tr><td>Tax (7.5%)</td><td style="text-align:right;">{self._format_amount(tax)}</td></tr>
                <tr style="font-size:16px;font-weight:600;border-top:1px solid {BRAND_BORDER};">
                    <td style="padding-top:8px;">Total</td>
                    <td style="text-align:right;padding-top:8px;">{self._format_amount(total)}</td>
                </tr>
            </table>
        </div>
        <div style="border:1px solid {BRAND_BORDER};border-radius:10px;padding:20px;">
            <p style="margin:0 0 8px;font-weight:600;">Shipping to</p>
            <p style="margin:0;color:#6B7280;">{address_lines}</p>
        </div>
        <p style="margin-top:32px;">You can track your order anytime from your Shopsoma profile. Thank you for choosing African luxury.</p>
        """

        html_content = self._wrap_email("Order Confirmation", body_html, "Your Shopsoma order has been received.")
        return await self.send_email(email, name, subject, html_content)

    async def send_vendor_new_order_email(
        self,
        email: str,
        name: str,
        order_number: str,
        order_date: datetime,
        items: List[dict],
        total_payout: float,
        pickup_date: datetime
    ) -> bool:
        subject = f"New Order Received · {order_number}"
        items_table = self._build_vendor_items_table(items)
        pickup_date_str = pickup_date.strftime("%d %B %Y · %I:%M %p")

        body_html = f"""
        <p style="font-size:16px;">Hello {name or 'there'},</p>
        <p>You have received a new order on Shopsoma. Please prepare the items below for pickup.</p>
        <div style="margin:24px 0;padding:20px;border:1px solid {BRAND_BORDER};border-radius:10px;background:{BRAND_LIGHT};">
            <p style="margin:0;"><strong>Order Number:</strong> {order_number}</p>
            <p style="margin:4px 0;"><strong>Order Date:</strong> {order_date.strftime('%d %B %Y · %I:%M %p')}</p>
            <p style="margin:4px 0;"><strong>Pickup Scheduled:</strong> {pickup_date_str}</p>
        </div>
        <table style="width:100%;border-collapse:collapse;margin-bottom:24px;">
            <thead>
                <tr style="background:{BRAND_LIGHT};text-transform:uppercase;font-size:12px;letter-spacing:0.15em;color:#6B7280;">
                    <th style="padding:12px;text-align:left;">Item</th>
                    <th style="padding:12px;text-align:center;">Qty</th>
                    <th style="padding:12px;text-align:right;">Payout</th>
                </tr>
            </thead>
            <tbody>
                {items_table}
            </tbody>
        </table>
        <div style="border:1px solid {BRAND_BORDER};border-radius:10px;padding:20px;margin-bottom:24px;">
            <table style="width:100%;font-size:14px;">
                <tr style="font-size:16px;font-weight:600;">
                    <td>Total Payout</td>
                    <td style="text-align:right;">{self._format_amount(total_payout)}</td>
                </tr>
            </table>
        </div>
        <p style="text-align:center;margin-top:32px;">
            <a href="{settings.FRONTEND_BASE_URL}/vendor/orders" style="display:inline-block;padding:12px 24px;background:{BRAND_PRIMARY};color:#fff;text-decoration:none;border-radius:999px;font-weight:600;">
                View Order in Vendor Dashboard
            </a>
        </p>
        <p style="margin-top:24px;color:#6B7280;font-size:13px;">
            Need help? Reach out to our vendor support team at
            <a href="mailto:partnerships@shopsoma.com" style="color:{BRAND_PRIMARY};">partnerships@shopsoma.com</a>.
        </p>
        """

        html_content = self._wrap_email("New Order", body_html, f"New order {order_number} received.")
        return await self.send_email(email, name, subject, html_content)

    async def send_vendor_payout_request_email(
        self,
        email: str,
        name: str,
        payout_amount: float,
        requested_at: datetime,
        payout_method: Optional[str] = None,
        hold_days: Optional[int] = None,
    ) -> bool:
        subject = "Payout Request Received"
        request_date = requested_at.strftime("%d %B %Y - %I:%M %p")
        hold_note = ""
        if hold_days is not None:
            hold_note = f"<p style=\"margin:0;\">Hold period: {hold_days} day{'' if hold_days == 1 else 's'}</p>"

        method_line = payout_method or "Your default payout account"

        body_html = f"""
        <p style="font-size:16px;">Hello {name or 'there'},</p>
        <p>Your payout request has been received and is being reviewed.</p>
        <div style="margin:24px 0;padding:20px;border:1px solid {BRAND_BORDER};border-radius:10px;background:{BRAND_LIGHT};">
            <p style="margin:0;"><strong>Amount:</strong> {self._format_amount(payout_amount)}</p>
            <p style="margin:4px 0;"><strong>Requested at:</strong> {request_date}</p>
            <p style="margin:4px 0;"><strong>Destination:</strong> {method_line}</p>
            {hold_note}
        </div>
        <p style="text-align:center;margin-top:32px;">
            <a href="{settings.FRONTEND_BASE_URL}/vendor/earnings/withdrawals