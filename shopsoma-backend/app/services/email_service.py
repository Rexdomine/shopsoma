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
from decimal import Decimal
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

CURRENCY_SYMBOLS = {
    "NGN": "₦",
    "USD": "$",
}


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
    def _normalize_currency(currency: Optional[str]) -> str:
        normalized = (currency or "NGN").upper()
        return normalized if normalized in CURRENCY_SYMBOLS else "NGN"

    @staticmethod
    def _as_decimal(value: Any) -> Decimal:
        if isinstance(value, Decimal):
            return value
        if value is None:
            return Decimal("0.00")
        return Decimal(str(value))

    @classmethod
    def _format_amount(cls, amount: float, currency: Optional[str] = "NGN") -> str:
        normalized = cls._normalize_currency(currency)
        symbol = CURRENCY_SYMBOLS.get(normalized, f"{normalized} ")
        formatted = f"{cls._as_decimal(amount):,.2f}"
        if symbol.endswith(" "):
            return f"{symbol}{formatted}"
        return f"{symbol}{formatted}"

    def _build_pricing_summary(self, items: List[dict], subtotal: float, shipping: float, tax: float, total: float) -> str:
        currencies = sorted(
            {
                self._normalize_currency(item.get("currency"))
                for item in items
            }
        ) or ["NGN"]

        if len(currencies) == 1:
            currency = currencies[0]
            return f"""
            <div style="border:1px solid {BRAND_BORDER};border-radius:10px;padding:20px;margin-bottom:24px;">
                <table style="width:100%;font-size:14px;">
                    <tr><td>Subtotal</td><td style="text-align:right;">{self._format_amount(subtotal, currency)}</td></tr>
                    <tr><td>Shipping</td><td style="text-align:right;">{self._format_amount(shipping, currency)}</td></tr>
                    <tr><td>Tax (7.5%)</td><td style="text-align:right;">{self._format_amount(tax, currency)}</td></tr>
                    <tr style="font-size:16px;font-weight:600;border-top:1px solid {BRAND_BORDER};">
                        <td style="padding-top:8px;">Total</td>
                        <td style="text-align:right;padding-top:8px;">{self._format_amount(total, currency)}</td>
                    </tr>
                </table>
            </div>
            """

        subtotals_by_currency: Dict[str, Decimal] = {}
        for item in items:
            currency = self._normalize_currency(item.get("currency"))
            subtotals_by_currency.setdefault(currency, Decimal("0.00"))
            subtotals_by_currency[currency] += self._as_decimal(item.get("subtotal"))

        rows = "".join(
            f"""
            <tr>
                <td>{currency} Items Total</td>
                <td style="text-align:right;">{self._format_amount(amount, currency)}</td>
            </tr>
            """
            for currency, amount in sorted(subtotals_by_currency.items())
        )

        return f"""
        <div style="border:1px solid {BRAND_BORDER};border-radius:10px;padding:20px;margin-bottom:24px;">
            <p style="margin:0 0 12px;font-weight:600;">Currency Totals</p>
            <table style="width:100%;font-size:14px;">
                {rows}
            </table>
            <p style="margin:12px 0 0;color:#6B7280;font-size:12px;">
                Shipping, tax, and final total are not combined because this order contains multiple currencies.
            </p>
        </div>
        """

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
            currency = self._normalize_currency(item.get("currency"))
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
                <td style="padding:12px;border-bottom:1px solid {BRAND_BORDER};text-align:right;">{self._format_amount(item.get('price',0), currency)}</td>
                <td style="padding:12px;border-bottom:1px solid {BRAND_BORDER};text-align:right;">{self._format_amount(item.get('subtotal',0), currency)}</td>
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
        pricing_summary = self._build_pricing_summary(items, subtotal, shipping, tax, total)
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
        {pricing_summary}
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
            <a href="{settings.FRONTEND_BASE_URL}/vendor/earnings/withdrawals" style="display:inline-block;padding:12px 24px;background:{BRAND_PRIMARY};color:#fff;text-decoration:none;border-radius:999px;font-weight:600;">
                View Withdrawal Status
            </a>
        </p>
        <p style="margin-top:24px;color:#6B7280;font-size:13px;">
            Need help? Reach out to our vendor support team at
            <a href="mailto:partnerships@shopsoma.com" style="color:{BRAND_PRIMARY};">partnerships@shopsoma.com</a>.
        </p>
        """

        html_content = self._wrap_email("Payout Request", body_html, "Your payout request has been received.")
        return await self.send_email(email, name, subject, html_content)

    async def send_vendor_payout_processed_email(
        self,
        email: str,
        name: str,
        payout_amount: float,
        processed_at: datetime,
        payout_method: Optional[str] = None,
    ) -> bool:
        subject = "Payout Processed"
        processed_date = processed_at.strftime("%d %B %Y - %I:%M %p")
        method_line = payout_method or "Your default payout account"

        body_html = f"""
        <p style="font-size:16px;">Hello {name or 'there'},</p>
        <p>Your payout has been processed successfully.</p>
        <div style="margin:24px 0;padding:20px;border:1px solid {BRAND_BORDER};border-radius:10px;background:{BRAND_LIGHT};">
            <p style="margin:0;"><strong>Processed Date:</strong> {processed_date}</p>
            <p style="margin:4px 0;"><strong>Amount:</strong> {self._format_amount(payout_amount)}</p>
            <p style="margin:4px 0;"><strong>Method:</strong> {method_line}</p>
        </div>
        <p>If you have any questions about this payout, please contact support.</p>
        """

        html_content = self._wrap_email("Payout Processed", body_html, "Your Shopsoma payout has been sent.")
        return await self.send_email(email, name, subject, html_content)

    async def send_vendor_payout_failed_email(
        self,
        email: str,
        name: str,
        payout_amount: float,
        failure_reason: str,
    ) -> bool:
        subject = "Payout Failed"

        body_html = f"""
        <p style="font-size:16px;">Hello {name or 'there'},</p>
        <p>We attempted to process your payout but ran into an issue.</p>
        <div style="margin:24px 0;padding:20px;border:1px solid {BRAND_BORDER};border-radius:10px;background:{BRAND_LIGHT};">
            <p style="margin:0;"><strong>Amount:</strong> {self._format_amount(payout_amount)}</p>
            <p style="margin:4px 0;"><strong>Reason:</strong> {failure_reason}</p>
        </div>
        <p>Please update your payout details or contact support for assistance.</p>
        """

        html_content = self._wrap_email("Payout Failed", body_html, "Issue processing your Shopsoma payout.")
        return await self.send_email(email, name, subject, html_content)

    async def send_admin_payout_request_email(
        self,
        recipients: List[Dict[str, str]],
        vendor_name: str,
        vendor_email: str,
        payout_amount: float,
        requested_at: datetime,
        payout_id: str,
    ) -> bool:
        if not recipients:
            return False

        subject = f"New Payout Request - {vendor_name}"
        request_date = requested_at.strftime("%d %B %Y - %I:%M %p")

        body_html = f"""
        <p style="font-size:16px;">Hello Admin,</p>
        <p>A vendor has submitted a payout request.</p>
        <div style="margin:24px 0;padding:20px;border:1px solid {BRAND_BORDER};border-radius:10px;background:{BRAND_LIGHT};">
            <p style="margin:0;"><strong>Vendor:</strong> {vendor_name}</p>
            <p style="margin:4px 0;"><strong>Email:</strong> {vendor_email}</p>
            <p style="margin:4px 0;"><strong>Amount:</strong> {self._format_amount(payout_amount)}</p>
            <p style="margin:4px 0;"><strong>Requested at:</strong> {request_date}</p>
            <p style="margin:4px 0;"><strong>Payout ID:</strong> {payout_id}</p>
        </div>
        <p style="text-align:center;margin-top:32px;">
            <a href="{settings.FRONTEND_BASE_URL}/admin/payouts" style="display:inline-block;padding:12px 24px;background:{BRAND_PRIMARY};color:#fff;text-decoration:none;border-radius:999px;font-weight:600;">
                Review Payouts
            </a>
        </p>
        """

        html_content = self._wrap_email("Payout Request", body_html, "A new payout request is waiting.")

        sent_any = False
        for recipient in recipients:
            sent_any = await self.send_email(
                recipient["email"],
                recipient.get("name") or "Admin",
                subject,
                html_content,
            ) or sent_any
        return sent_any

    async def send_admin_order_notification(
        self,
        order_number: str,
        customer_name: str,
        customer_email: str,
        order_date: datetime,
        items: list,
        subtotal: float,
        shipping: float,
        tax: float,
        total: float,
        payment_status: str,
        shipping_address: Dict[str, str],
        recipients: Optional[List[Dict[str, str]]] = None
    ) -> bool:
        """
        Send new order notification to admin

        Args:
            order_number: Order number
            customer_name: Customer's full name
            customer_email: Customer's email
            order_date: When order was placed
            items: List of order items
            subtotal: Order subtotal
            shipping: Shipping cost
            tax: Tax amount
            total: Total amount
            payment_status: Payment status (paid, pending, etc.)
            shipping_address: Shipping address dict
            recipients: Optional list of {"email": str, "name": str} recipients

        Returns:
            bool: True if email sent successfully
        """
        from app.core.config import settings

        subject = f"New Order Alert · {order_number}"
        items_table = self._build_items_table(items)
        pricing_summary = self._build_pricing_summary(items, subtotal, shipping, tax, total)

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

        # Payment status badge
        payment_badge_colors = {
            'paid': '#19984B',
            'pending': '#D97706',
            'failed': '#DC2626',
        }
        payment_color = payment_badge_colors.get(payment_status.lower(), '#6B7280')

        body_html = f"""
        <p style="font-size:16px;">New order received on Shopsoma.</p>
        <div style="margin:24px 0;padding:20px;border:1px solid {BRAND_BORDER};border-radius:10px;background:{BRAND_LIGHT};">
            <p style="margin:0;"><strong>Order Number:</strong> {order_number}</p>
            <p style="margin:4px 0;"><strong>Order Date:</strong> {order_date.strftime('%d %B %Y · %I:%M %p')}</p>
            <p style="margin:4px 0;"><strong>Payment Status:</strong> <span style="color:{payment_color};font-weight:600;">{payment_status.upper()}</span></p>
        </div>
        <div style="border:1px solid {BRAND_BORDER};border-radius:10px;padding:20px;margin-bottom:24px;">
            <p style="margin:0 0 8px;font-weight:600;">Customer Information</p>
            <p style="margin:0;color:#6B7280;"><strong>Name:</strong> {customer_name}</p>
            <p style="margin:4px 0;color:#6B7280;"><strong>Email:</strong> {customer_email}</p>
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
        {pricing_summary}
        <div style="border:1px solid {BRAND_BORDER};border-radius:10px;padding:20px;">
            <p style="margin:0 0 8px;font-weight:600;">Shipping Address</p>
            <p style="margin:0;color:#6B7280;">{address_lines}</p>
        </div>
        <p style="text-align:center;margin-top:32px;">
            <a href="{settings.FRONTEND_BASE_URL}/admin/orders" style="display:inline-block;padding:12px 24px;background:{BRAND_PRIMARY};color:#fff;text-decoration:none;border-radius:999px;font-weight:600;">
                View in Admin Dashboard
            </a>
        </p>
        """

        html_content = self._wrap_email("New Order", body_html, f"New order {order_number} from {customer_name}")
        recipient_list = recipients or [{"email": settings.ADMIN_EMAIL, "name": "Admin"}]
        all_sent = True
        for recipient in recipient_list:
            sent = await self.send_email(
                recipient.get("email", settings.ADMIN_EMAIL),
                recipient.get("name", "Admin"),
                subject,
                html_content
            )
            all_sent = all_sent and sent
        return all_sent

    async def send_order_status_update_email(
        self,
        email: str,
        name: str,
        order_number: str,
        status: str,
        tracking_number: Optional[str] = None
    ) -> bool:
        subject = f"Order Update · {order_number}"
        status_messages = {
            "processing": "We're perfecting your order. Expect a shipping update soon.",
            "shipped": f"Your order is en route. Tracking number: <strong>{tracking_number}</strong>",
            "delivered": "Delivered! We hope you love your new pieces.",
            "cancelled": "Your order has been cancelled. Refunds (if applicable) will be processed shortly."
        }
        message = status_messages.get(status.lower(), "Your order status has been updated.")

        body_html = f"""
        <p style="font-size:16px;">Hi {name or 'there'},</p>
        <p>{message}</p>
        <div style="border:1px solid {BRAND_BORDER};border-radius:10px;padding:20px;margin:24px 0;">
            <p style="margin:0 0 6px;"><strong>Order:</strong> {order_number}</p>
            <p style="margin:0;color:#6B7280;">Status: {status.title()}</p>
            {f'<p style="margin:6px 0 0;color:#6B7280;">Tracking: {tracking_number}</p>' if tracking_number else ''}
        </div>
        <p style="text-align:center;margin-top:32px;">
            <a href="https://shopsoma.com/profile/orders" style="display:inline-block;padding:12px 24px;border:1px solid {BRAND_PRIMARY};color:{BRAND_PRIMARY};text-decoration:none;border-radius:999px;font-weight:600;">
                Track Order
            </a>
        </p>
        """

        html_content = self._wrap_email("Order Update", body_html, "Your Shopsoma order status has changed.")
        return await self.send_email(email, name, subject, html_content)

    async def send_payment_receipt_email(
        self,
        email: str,
        name: str,
        order_number: str,
        amount: float,
        payment_method: str,
        reference: str,
        currency: str = "NGN",
    ) -> bool:
        subject = f"Payment Receipt · {order_number}"
        body_html = f"""
        <p style="font-size:16px;">Hello {name or 'there'},</p>
        <p>Thank you for your purchase. This is a confirmation that we successfully received your payment.</p>
        <div style="border:1px solid {BRAND_BORDER};border-radius:10px;padding:20px;margin:24px 0;background:{BRAND_LIGHT};">
            <table style="width:100%;font-size:14px;">
                <tr><td>Order number</td><td style="text-align:right;">{order_number}</td></tr>
                <tr><td>Amount paid</td><td style="text-align:right;">{self._format_amount(amount, currency)}</td></tr>
                <tr><td>Payment method</td><td style="text-align:right;">{payment_method}</td></tr>
                <tr><td>Reference</td><td style="text-align:right;">{reference}</td></tr>
                <tr><td>Date</td><td style="text-align:right;">{datetime.now().strftime('%d %B %Y')}</td></tr>
            </table>
        </div>
        <p>Keep this receipt for your records. If anything looks incorrect please contact support immediately.</p>
        """
        html_content = self._wrap_email("Payment Receipt", body_html, "Payment confirmed for your Shopsoma order.")
        return await self.send_email(email, name, subject, html_content)

    async def send_verification_email(self, email: str, name: str, verification_link: str) -> bool:
        """Send email verification link"""
        subject = "Verify Your Email · Shopsoma"
        body_html = f"""
        <p style="font-size:16px;">Hi {name or 'there'},</p>
        <p>Thank you for registering with Shopsoma. Please verify your email address to complete your account setup and start shopping.</p>
        <div style="margin:32px 0;text-align:center;">
            <a href="{verification_link}" style="display:inline-block;padding:14px 32px;background:{BRAND_PRIMARY};color:#fff;border-radius:999px;text-decoration:none;font-weight:600;font-size:16px;">
                Verify Email Address
            </a>
        </div>
        <p style="color:#6B7280;font-size:14px;">This verification link will expire in 24 hours. If you didn't create an account with Shopsoma, you can safely ignore this email.</p>
        <p style="color:#6B7280;font-size:14px;">If the button doesn't work, copy and paste this link into your browser:</p>
        <p style="color:{BRAND_PRIMARY};font-size:12px;word-break:break-all;">{verification_link}</p>
        """
        html_content = self._wrap_email("Verify Your Email", body_html, "Complete your Shopsoma registration by verifying your email.")
        return await self.send_email(email, name, subject, html_content)

    async def send_account_claim_email(self, email: str, name: str, claim_link: str) -> bool:
        """Send account claim / password setup email for silently created guest accounts."""
        subject = "Secure Your Shopsoma Account"
        body_html = f"""
        <p style="font-size:16px;">Hi {name or 'there'},</p>
        <p>Thanks for shopping with Shopsoma. We created a secure profile for you so your order history and saved preferences stay in sync.</p>
        <p>Set a password now to unlock faster checkout, saved addresses, and priority support.</p>
        <div style="margin:32px 0;text-align:center;">
            <a href="{claim_link}" style="display:inline-block;padding:14px 32px;background:{BRAND_PRIMARY};color:#fff;border-radius:999px;text-decoration:none;font-weight:600;font-size:16px;">
                Set Your Password
            </a>
        </div>
        <p style="color:#6B7280;font-size:14px;">This secure link expires in 7 days. If it expires or you prefer a fresh link, you can request another anytime from the checkout or profile pages.</p>
        <p style="color:#6B7280;font-size:14px;">If the button doesn't work, copy and paste this link into your browser:</p>
        <p style="color:{BRAND_PRIMARY};font-size:12px;word-break:break-all;">{claim_link}</p>
        <p>We're excited to keep curating premium African fashion for you.</p>
        """
        preheader = "Activate your Shopsoma account in seconds for faster checkout."
        html_content = self._wrap_email("Claim Your Account", body_html, preheader)
        return await self.send_email(email, name, subject, html_content)

    async def send_password_reset_email(
        self,
        email: str,
        name: str,
        reset_link: str,
        expires_minutes: int
    ) -> bool:
        """Send password reset email."""
        subject = "Reset Your Password · Shopsoma"
        body_html = f"""
        <p style="font-size:16px;">Hi {name or 'there'},</p>
        <p>We received a request to reset your Shopsoma password. Use the button below to set a new password.</p>
        <div style="margin:32px 0;text-align:center;">
            <a href="{reset_link}" style="display:inline-block;padding:14px 32px;background:{BRAND_PRIMARY};color:#fff;border-radius:999px;text-decoration:none;font-weight:600;font-size:16px;">
                Reset Password
            </a>
        </div>
        <p style="color:#6B7280;font-size:14px;">This link expires in {expires_minutes} minutes. If you didn't request a password reset, you can safely ignore this email.</p>
        <p style="color:#6B7280;font-size:14px;">If the button doesn't work, copy and paste this link into your browser:</p>
        <p style="color:{BRAND_PRIMARY};font-size:12px;word-break:break-all;">{reset_link}</p>
        """
        preheader = "Use this secure link to reset your Shopsoma password."
        html_content = self._wrap_email("Reset Password", body_html, preheader)
        return await self.send_email(email, name, subject, html_content)

    async def send_vendor_application_confirmation(self, email: str, first_name: str, business_name: str) -> bool:
        """Send confirmation email when vendor application is submitted"""
        subject = "Application Received - Shopsoma Vendor Program"
        body_html = f"""
        <p style="font-size:16px;">Hi {first_name},</p>
        <p>Thank you for applying to become a vendor on Shopsoma! We're excited to review your application for <strong>{business_name}</strong>.</p>
        <div style="border:1px solid {BRAND_BORDER};border-radius:10px;padding:20px;margin:24px 0;background:{BRAND_LIGHT};">
            <p style="margin:0 0 12px;font-weight:600;">What happens next?</p>
            <ul style="padding-left:20px;margin:0;color:{BRAND_DARK};">
                <li style="margin-bottom:8px;">Our team will review your application within 3-5 business days</li>
                <li style="margin-bottom:8px;">We'll verify your business information and brand story</li>
                <li style="margin-bottom:8px;">You'll receive an email with our decision</li>
                <li>If approved, you'll get access to your vendor dashboard</li>
            </ul>
        </div>
        <p>We receive many applications from talented designers across Africa, and we carefully review each one to ensure the best experience for our customers.</p>
        <p style="color:#6B7280;font-size:14px;margin-top:24px;">
            <strong>Need to update your application?</strong> Please reply to this email with any changes or additional information.
        </p>
        <p>Thank you for your interest in joining the Shopsoma community. We're building Africa's premier luxury fashion marketplace, one designer at a time.</p>
        """
        preheader = "Your vendor application has been received and is under review."
        html_content = self._wrap_email("Application Received", body_html, preheader)
        return await self.send_email(email, first_name, subject, html_content)

    async def send_vendor_application_rejection(self, email: str, first_name: str, business_name: str, reason: str = None) -> bool:
        """Send rejection email when vendor application is declined"""
        subject = "Vendor Application Update - Shopsoma"

        reason_html = ""
        if reason and reason.strip():
            reason_html = f"""
            <div style="border:1px solid {BRAND_BORDER};border-radius:10px;padding:20px;margin:24px 0;background:{BRAND_LIGHT};">
                <p style="margin:0 0 8px;font-weight:600;color:{BRAND_DARK};">Feedback from our team:</p>
                <p style="margin:0;color:#6B7280;font-style:italic;">"{reason}"</p>
            </div>
            """

        body_html = f"""
        <p style="font-size:16px;">Hi {first_name},</p>
        <p>Thank you for your interest in joining Shopsoma as a vendor. We've carefully reviewed your application for <strong>{business_name}</strong>.</p>
        <p>Unfortunately, we're unable to approve your application at this time. We receive many applications from talented designers and have to be selective to maintain the quality our customers expect.</p>
        {reason_html}
        <div style="border:1px solid {BRAND_BORDER};border-radius:10px;padding:20px;margin:24px 0;background:{BRAND_LIGHT};">
            <p style="margin:0 0 12px;font-weight:600;">What you can do:</p>
            <ul style="padding-left:20px;margin:0;color:{BRAND_DARK};">
                <li style="margin-bottom:8px;">Review and improve your brand story and product offerings</li>
                <li style="margin-bottom:8px;">Build your online presence and customer reviews</li>
                <li style="margin-bottom:8px;">Reapply in the future when your business has grown</li>
            </ul>
        </div>
        <p>We appreciate your interest in Shopsoma and wish you success with your business. Feel free to reach out if you have any questions.</p>
        <p style="color:#6B7280;font-size:14px;margin-top:24px;">
            If you believe this decision was made in error or would like more information, please reply to this email.
        </p>
        """
        preheader = "Update on your Shopsoma vendor application"
        html_content = self._wrap_email("Application Update", body_html, preheader)
        return await self.send_email(email, first_name, subject, html_content)

    async def send_vendor_otp_email(self, email: str, otp_code: str, expiry_minutes: int = 15) -> bool:
        """Send vendor activation OTP code via email"""
        subject = "Your Shopsoma Designer Verification Code"

        # Get the activation link with email parameter
        frontend_url = getattr(settings, 'FRONTEND_BASE_URL', 'http://localhost:5173')
        activation_link = f"{frontend_url}/vendor/otp?email={email}"

        body_html = f"""
        <div style="text-align:center;margin:32px 0;">
            <div style="display:inline-block;background:{BRAND_LIGHT};border:2px solid {BRAND_BORDER};border-radius:12px;padding:24px 48px;">
                <p style="font-size:14px;color:{BRAND_DARK};margin:0 0 12px 0;text-transform:uppercase;letter-spacing:1px;font-weight:600;">Verification Code</p>
                <p style="font-size:42px;font-weight:700;color:{BRAND_PRIMARY};margin:0;letter-spacing:8px;font-family:monospace;">{otp_code}</p>
            </div>
        </div>
        <p style="font-size:16px;">Welcome to Shopsoma!</p>
        <p>You're almost ready to start showcasing your designs to thousands of fashion enthusiasts across Africa.</p>
        <p>Click the button below to activate your vendor account, then enter the verification code above:</p>
        <div style="text-align:center;margin:32px 0;">
            <a href="{activation_link}" style="display:inline-block;padding:16px 32px;background:{BRAND_PRIMARY};color:#ffffff;text-decoration:none;border-radius:8px;font-weight:600;font-size:16px;">Activate My Account</a>
        </div>
        <p style="color:#6B7280;font-size:14px;margin-top:24px;">
            <strong>Security reminder:</strong> This code expires in {expiry_minutes} minutes and is for one-time use only.
            Never share this code with anyone - Shopsoma staff will never ask for it.
        </p>
        <p style="color:#6B7280;font-size:14px;">If the button doesn't work, copy and paste this link into your browser:</p>
        <p style="color:{BRAND_PRIMARY};font-size:12px;word-break:break-all;">{activation_link}</p>
        <p>Questions? Contact our vendor support team at support@shopsoma.com.</p>
        """
        preheader = f"Your verification code is {otp_code}. Enter it to activate your vendor account."
        html_content = self._wrap_email("Activate Your Vendor Account", body_html, preheader)
        return await self.send_email(email, "Vendor", subject, html_content)

    async def send_vendor_store_restored_email(self, email: str, vendor_name: str, business_name: str) -> bool:
        """Send notification email when vendor store is restored by admin"""
        subject = "Your Shopsoma Store Has Been Restored"

        # Get vendor dashboard link
        frontend_url = getattr(settings, 'FRONTEND_BASE_URL', 'http://localhost:5173')
        dashboard_link = f"{frontend_url}/vendor/dashboard"

        body_html = f"""
        <p style="font-size:16px;">Hi {vendor_name},</p>
        <p>Great news! Your Shopsoma store <strong>{business_name}</strong> has been successfully restored and is now active again.</p>
        <div style="border:1px solid {BRAND_BORDER};border-radius:10px;padding:20px;margin:24px 0;background:{BRAND_LIGHT};">
            <p style="margin:0 0 12px;font-weight:600;">What this means:</p>
            <ul style="padding-left:20px;margin:0;color:{BRAND_DARK};">
                <li style="margin-bottom:8px;">Your products are now visible to customers</li>
                <li style="margin-bottom:8px;">You can accept new orders</li>
                <li style="margin-bottom:8px;">Your store profile is back online</li>
                <li>All your previous data and settings have been preserved</li>
            </ul>
        </div>
        <p>You can now log in to your vendor dashboard to manage your products, view orders, and update your store settings.</p>
        <div style="text-align:center;margin:32px 0;">
            <a href="{dashboard_link}" style="display:inline-block;padding:16px 32px;background:{BRAND_PRIMARY};color:#ffffff;text-decoration:none;border-radius:8px;font-weight:600;font-size:16px;">Go to Dashboard</a>
        </div>
        <p style="color:#6B7280;font-size:14px;margin-top:24px;">
            <strong>Need help getting started?</strong> Our vendor support team is here to assist you. Reply to this email or contact us at support@shopsoma.com.
        </p>
        <p>Welcome back! We're excited to continue showcasing your designs to our community of fashion enthusiasts.</p>
        """
        preheader = f"Your store {business_name} is now active and ready to accept orders."
        html_content = self._wrap_email("Store Restored", body_html, preheader)
        return await self.send_email(email, vendor_name, subject, html_content)

    async def send_product_approved_email(
        self,
        email: str,
        vendor_name: str,
        product_title: str,
        product_id: str,
        notes: Optional[str] = None
    ) -> bool:
        """
        Send product approval notification to vendor

        Args:
            email: Vendor email
            vendor_name: Vendor name
            product_title: Title of the approved product
            product_id: Product UUID
            notes: Optional approval notes from admin
        """
        subject = f"🎉 Product Approved: {product_title}"

        product_link = f"{settings.FRONTEND_URL}/vendor/products/{product_id}/view"
        dashboard_link = f"{settings.FRONTEND_URL}/vendor/products"

        notes_section = f"""
        <div style="background: {BRAND_LIGHT}; padding: 16px; border-radius: 8px; margin: 20px 0;">
            <p style="margin: 0; font-size: 14px; color: {BRAND_DARK};"><strong>Admin Notes:</strong></p>
            <p style="margin: 8px 0 0; font-size: 14px; color: #4B5563;">{notes}</p>
        </div>
        """ if notes else ""

        body_html = f"""
        <p style="font-size:16px;">Hi {vendor_name},</p>
        <p style="font-size:16px;margin-top:16px;">
            Great news! Your product <strong>"{product_title}"</strong> has been approved and is now live on Shopsoma.
        </p>
        {notes_section}
        <div style="background: #E8F7EF; padding: 20px; border-radius: 8px; margin: 24px 0; border-left: 4px solid {BRAND_PRIMARY};">
            <p style="margin: 0; font-size: 14px; color: {BRAND_DARK};">
                <strong>✓ Your product is now visible to customers</strong><br>
                Shoppers can now discover, view, and purchase your product.
            </p>
        </div>
        <div style="text-align:center;margin:32px 0;">
            <a href="{product_link}" style="display:inline-block;padding:16px 32px;background:{BRAND_PRIMARY};color:#ffffff;text-decoration:none;border-radius:8px;font-weight:600;font-size:16px;margin-right:12px;">View Product</a>
            <a href="{dashboard_link}" style="display:inline-block;padding:16px 32px;background:#ffffff;color:{BRAND_PRIMARY};text-decoration:none;border-radius:8px;font-weight:600;font-size:16px;border:2px solid {BRAND_PRIMARY};">Go to Dashboard</a>
        </div>
        <p style="color:#6B7280;font-size:14px;margin-top:24px;">
            Keep adding amazing products to grow your store! If you have any questions, our support team is here to help.
        </p>
        """
        preheader = f"Your product '{product_title}' is now live and available to customers."
        html_content = self._wrap_email("Product Approved", body_html, preheader)
        return await self.send_email(email, vendor_name, subject, html_content)

    async def send_product_rejected_email(
        self,
        email: str,
        vendor_name: str,
        product_title: str,
        product_id: str,
        reason: str,
        notes: Optional[str] = None
    ) -> bool:
        """
        Send product rejection notification to vendor

        Args:
            email: Vendor email
            vendor_name: Vendor name
            product_title: Title of the rejected product
            product_id: Product UUID
            reason: Rejection reason (required)
            notes: Optional additional notes from admin
        """
        subject = f"Product Review Update: {product_title}"

        product_link = f"{settings.FRONTEND_URL}/vendor/products/{product_id}/edit"
        guidelines_link = f"{settings.FRONTEND_URL}/vendor/guidelines"
        support_email = "support@shopsoma.com"

        notes_section = f"""
        <div style="background: {BRAND_LIGHT}; padding: 16px; border-radius: 8px; margin: 20px 0;">
            <p style="margin: 0; font-size: 14px; color: {BRAND_DARK};"><strong>Additional Notes:</strong></p>
            <p style="margin: 8px 0 0; font-size: 14px; color: #4B5563;">{notes}</p>
        </div>
        """ if notes else ""

        body_html = f"""
        <p style="font-size:16px;">Hi {vendor_name},</p>
        <p style="font-size:16px;margin-top:16px;">
            Thank you for submitting <strong>"{product_title}"</strong> for review. After careful consideration, we're unable to approve this product at this time.
        </p>

        <div style="background: #FEF2F2; padding: 20px; border-radius: 8px; margin: 24px 0; border-left: 4px solid #DC2626;">
            <p style="margin: 0; font-size: 14px; color: {BRAND_DARK};"><strong>Reason for Rejection:</strong></p>
            <p style="margin: 12px 0 0; font-size: 14px; color: #4B5563; line-height: 1.6;">{reason}</p>
        </div>
        {notes_section}

        <div style="background: #FFFBEB; padding: 20px; border-radius: 8px; margin: 24px 0; border-left: 4px solid #F59E0B;">
            <p style="margin: 0; font-size: 14px; color: {BRAND_DARK};"><strong>What's Next?</strong></p>
            <ul style="margin: 12px 0 0; padding-left: 20px; font-size: 14px; color: #4B5563;">
                <li style="margin-bottom: 8px;">Review our product guidelines to understand our quality standards</li>
                <li style="margin-bottom: 8px;">Make the necessary changes to your product</li>
                <li style="margin-bottom: 8px;">Resubmit for review - we're here to help you succeed!</li>
            </ul>
        </div>

        <div style="text-align:center;margin:32px 0;">
            <a href="{product_link}" style="display:inline-block;padding:16px 32px;background:{BRAND_PRIMARY};color:#ffffff;text-decoration:none;border-radius:8px;font-weight:600;font-size:16px;margin-right:12px;">Edit Product</a>
            <a href="{guidelines_link}" style="display:inline-block;padding:16px 32px;background:#ffffff;color:{BRAND_PRIMARY};text-decoration:none;border-radius:8px;font-weight:600;font-size:16px;border:2px solid {BRAND_PRIMARY};">View Guidelines</a>
        </div>

        <p style="color:#6B7280;font-size:14px;margin-top:24px;">
            <strong>Need help?</strong> If you have questions about this decision or need guidance on how to improve your product, please reach out to our support team at <a href="mailto:{support_email}" style="color:{BRAND_PRIMARY};">{support_email}</a>. We're here to support your success!
        </p>
        """
        preheader = f"Your product '{product_title}' needs some updates before it can go live."
        html_content = self._wrap_email("Product Review Update", body_html, preheader)
        return await self.send_email(email, vendor_name, subject, html_content)


email_service = EmailService()
