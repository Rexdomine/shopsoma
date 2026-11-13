"""Promo code evaluation and redemption tracking service."""

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order import Order, PaymentStatus
from app.models.promo_code import DiscountType, PromoCode
from app.models.setting import Setting
from app.models.user import User

DEFAULT_USD_TO_NGN_RATE = Decimal("833")


@dataclass
class PromoEvaluationResult:
    valid: bool
    promo: Optional[PromoCode] = None
    code: Optional[str] = None
    discount_type: Optional[DiscountType] = None
    discount_value: Optional[Decimal] = None
    discount_amount: Decimal = Decimal("0.00")
    currency: str = "NGN"
    message: Optional[str] = None


def normalize_promo_currency(currency: Optional[str]) -> str:
    normalized = (currency or "NGN").strip().upper()
    return normalized if normalized in {"NGN", "USD"} else "NGN"


def _normalize_dt(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


async def get_usd_to_ngn_rate(db: AsyncSession) -> Decimal:
    result = await db.execute(
        select(Setting).where(Setting.key == "exchange_rate_usd_to_ngn")
    )
    rate_setting = result.scalar_one_or_none()
    if not rate_setting:
        return DEFAULT_USD_TO_NGN_RATE

    try:
        rate = Decimal(str(rate_setting.value))
        return rate if rate > 0 else DEFAULT_USD_TO_NGN_RATE
    except (ArithmeticError, ValueError, TypeError):
        return DEFAULT_USD_TO_NGN_RATE


def convert_promo_money(
    amount: Decimal,
    from_currency: str,
    to_currency: str,
    usd_to_ngn_rate: Decimal,
) -> Decimal:
    source = normalize_promo_currency(from_currency)
    target = normalize_promo_currency(to_currency)
    if source == target:
        return amount.quantize(Decimal("0.01"))
    if source == "USD" and target == "NGN":
        return (amount * usd_to_ngn_rate).quantize(Decimal("0.01"))
    if source == "NGN" and target == "USD":
        return (amount / usd_to_ngn_rate).quantize(Decimal("0.01"))
    return amount.quantize(Decimal("0.01"))


def format_promo_money(amount: Decimal, currency: str) -> str:
    symbol = "$" if normalize_promo_currency(currency) == "USD" else "₦"
    return f"{symbol}{amount:,.2f}"


async def evaluate_promo_code(
    db: AsyncSession,
    code: Optional[str],
    subtotal: Decimal,
    currency: str = "NGN",
    usd_to_ngn_rate: Optional[Decimal] = None,
    user_id: Optional[UUID] = None,
    customer_email: Optional[str] = None,
    now: Optional[datetime] = None,
) -> PromoEvaluationResult:
    checkout_currency = normalize_promo_currency(currency)
    cleaned_code = (code or "").strip().upper()
    if not cleaned_code:
        return PromoEvaluationResult(
            valid=False,
            currency=checkout_currency,
            message="Promo code is required",
        )

    result = await db.execute(
        select(PromoCode).where(PromoCode.code == cleaned_code)
    )
    promo = result.scalar_one_or_none()
    if not promo:
        return PromoEvaluationResult(
            valid=False,
            currency=checkout_currency,
            message=f"Promo code '{cleaned_code}' not found",
        )

    if not promo.is_active:
        return PromoEvaluationResult(
            valid=False,
            code=promo.code,
            currency=checkout_currency,
            message="Promo code is inactive",
        )

    current_time = _normalize_dt(now or datetime.now(timezone.utc))
    valid_from = _normalize_dt(promo.valid_from)
    valid_until = _normalize_dt(promo.valid_until)

    if current_time < valid_from:
        return PromoEvaluationResult(
            valid=False,
            code=promo.code,
            currency=checkout_currency,
            message=f"Promo code not yet valid. Valid from {valid_from.strftime('%Y-%m-%d')}",
        )

    if current_time > valid_until:
        return PromoEvaluationResult(
            valid=False,
            code=promo.code,
            currency=checkout_currency,
            message=f"Promo code expired on {valid_until.strftime('%Y-%m-%d')}",
        )

    if promo.usage_limit is not None and (promo.usage_count or 0) >= promo.usage_limit:
        return PromoEvaluationResult(
            valid=False,
            code=promo.code,
            currency=checkout_currency,
            message="Promo code usage limit reached",
        )

    effective_user_id = user_id
    if effective_user_id is None and customer_email:
        cleaned_email = customer_email.strip().lower()
        if cleaned_email:
            user_result = await db.execute(
                select(User.id).where(func.lower(User.email) == cleaned_email)
            )
            effective_user_id = user_result.scalar_one_or_none()

    if effective_user_id is not None and promo.usage_limit_per_user is not None:
        user_usage_result = await db.execute(
            select(func.count(Order.id)).where(
                Order.customer_id == effective_user_id,
                Order.promo_code_id == promo.id,
                or_(
                    Order.promo_usage_counted == True,
                    Order.payment_status == PaymentStatus.PAID,
                ),
            )
        )
        user_usage_count = int(user_usage_result.scalar() or 0)
        if user_usage_count >= promo.usage_limit_per_user:
            return PromoEvaluationResult(
                valid=False,
                code=promo.code,
                currency=checkout_currency,
                message="You have already reached the usage limit for this promo code",
            )

    rate = usd_to_ngn_rate if usd_to_ngn_rate is not None else await get_usd_to_ngn_rate(db)
    subtotal_dec = Decimal(subtotal).quantize(Decimal("0.01"))

    if promo.min_purchase_amount is not None and promo.min_purchase_amount > Decimal("0.00"):
        min_required = convert_promo_money(
            Decimal(promo.min_purchase_amount),
            "NGN",
            checkout_currency,
            rate,
        )
        if subtotal_dec < min_required:
            return PromoEvaluationResult(
                valid=False,
                code=promo.code,
                currency=checkout_currency,
                message=f"Minimum purchase amount of {format_promo_money(min_required, checkout_currency)} required",
            )

    discount_amount = Decimal("0.00")
    if promo.discount_type == DiscountType.PERCENTAGE:
        discount_amount = (
            (subtotal_dec * Decimal(promo.discount_value)) / Decimal("100")
        ).quantize(Decimal("0.01"))
        if promo.max_discount_amount is not None and promo.max_discount_amount > Decimal("0.00"):
            max_cap = convert_promo_money(
                Decimal(promo.max_discount_amount),
                "NGN",
                checkout_currency,
                rate,
            )
            if discount_amount > max_cap:
                discount_amount = max_cap
    elif promo.discount_type == DiscountType.FIXED_AMOUNT:
        discount_amount = convert_promo_money(
            Decimal(promo.discount_value),
            "NGN",
            checkout_currency,
            rate,
        )

    if discount_amount < Decimal("0.00"):
        discount_amount = Decimal("0.00")
    if discount_amount > subtotal_dec:
        discount_amount = subtotal_dec
    discount_amount = discount_amount.quantize(Decimal("0.01"))

    return PromoEvaluationResult(
        valid=True,
        promo=promo,
        code=promo.code,
        discount_type=promo.discount_type,
        discount_value=promo.discount_value,
        discount_amount=discount_amount,
        currency=checkout_currency,
        message=f"{format_promo_money(discount_amount, checkout_currency)} discount applied",
    )


async def record_order_promo_redemption(db: AsyncSession, order: Order) -> bool:
    """Atomically increment promo_codes.usage_count once per paid order."""
    if not order.promo_code_id or order.promo_usage_counted:
        return False

    claim = await db.execute(
        update(Order)
        .where(
            Order.id == order.id,
            Order.promo_usage_counted == False,
        )
        .values(promo_usage_counted=True)
    )
    if (claim.rowcount or 0) == 0:
        order.promo_usage_counted = True
        return False

    await db.execute(
        update(PromoCode)
        .where(PromoCode.id == order.promo_code_id)
        .values(usage_count=func.coalesce(PromoCode.usage_count, 0) + 1)
    )
    order.promo_usage_counted = True
    return True
