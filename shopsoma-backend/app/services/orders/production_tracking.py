"""Made-to-order production tracking and platform working-day calendar rules.

Rules:
- Working days are Monday through Friday (weekday < 5).
- Non-working days are Saturday and Sunday.
- Production start date is derived from order confirmation (order.confirmed_at),
  falling back to order creation (order.created_at) or item creation (item.created_at).
- Target production due date adds the configured working days to the start date,
  skipping non-working weekend days.
- Working days left counts the business days between the evaluation date (as_of)
  and the target due date.
- The countdown is informational only and does not block vendor readiness actions.
- Ready-to-wear (RTW) items return None / no countdown data.
- Completed items (ready_for_pickup_at set) are identified as completed rather
  than actively counting down.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
import re
from typing import Optional, Union

from app.models.order import Order, OrderItem
from app.models.vendor_pickup import VendorPickup
from app.services.orders.made_to_order_readiness import is_made_to_order_item


def is_working_day(target_date: Union[date, datetime]) -> bool:
    """Return True if target_date falls on a working day (Monday through Friday)."""
    if isinstance(target_date, datetime):
        target_date = target_date.date()
    return target_date.weekday() < 5


def add_working_days(start: Union[date, datetime], working_days: int) -> date:
    """Add N working days to start date, skipping weekends.

    If start date falls on a weekend, counting starts from the subsequent working day.
    """
    if isinstance(start, datetime):
        cur = start.date()
    else:
        cur = start

    if working_days <= 0:
        return cur

    added = 0
    while added < working_days:
        cur += timedelta(days=1)
        if cur.weekday() < 5:
            added += 1
    return cur


def count_working_days_between(d1: Union[date, datetime], d2: Union[date, datetime]) -> int:
    """Count working days between d1 and d2.

    If d1 == d2: returns 0.
    If d1 < d2: returns positive count of working days after d1 up to and including d2.
    If d1 > d2: returns negative count of working days after d2 up to and including d1.
    """
    start_d = d1.date() if isinstance(d1, datetime) else d1
    end_d = d2.date() if isinstance(d2, datetime) else d2

    if start_d == end_d:
        return 0

    if start_d < end_d:
        cur = start_d
        count = 0
        while cur < end_d:
            cur += timedelta(days=1)
            if cur.weekday() < 5:
                count += 1
        return count
    else:
        cur = end_d
        count = 0
        while cur < start_d:
            cur += timedelta(days=1)
            if cur.weekday() < 5:
                count += 1
        return -count


def parse_production_days(
    timeline: Optional[str],
    estimated_days: Optional[int] = None,
) -> Optional[int]:
    """Extract integer working days from an explicit integer or string timeline.

    Handles formats such as:
    - 7 -> 7
    - '5-7 business days' -> 7
    - '10 working days' -> 10
    - '2-3 weeks' -> 15 (upper bound: 3 weeks * 5 working days)
    - '2 weeks' -> 10 (2 weeks * 5 working days)
    - '14 days' -> 14
    - '14' -> 14
    """
    if estimated_days is not None and estimated_days > 0:
        return int(estimated_days)

    if not timeline or not isinstance(timeline, str):
        return None

    cleaned = timeline.strip().lower()
    if not cleaned:
        return None

    # Check for week-based patterns: '2-3 weeks', '3 weeks', '2 to 3 weeks'
    m_weeks = re.search(r'(?:(\d+)\s*(?:-|to)\s*)?(\d+)\s*weeks?', cleaned)
    if m_weeks:
        upper_weeks = int(m_weeks.group(2))
        return upper_weeks * 5  # 5 working days per week

    # Check for day-based patterns: '5-7 business days', '7 days', '10 working days'
    m_days = re.search(r'(?:(\d+)\s*(?:-|to)\s*)?(\d+)\s*(?:business|working)?\s*days?', cleaned)
    if m_days:
        upper_days = int(m_days.group(2))
        return upper_days

    # Standalone integer
    m_num = re.search(r'^(\d+)$', cleaned)
    if m_num:
        return int(m_num.group(1))

    return None


def get_production_tracking(
    item: OrderItem,
    pickup: Optional[VendorPickup],
    order: Optional[Order] = None,
    as_of: Optional[datetime] = None,
) -> dict:
    """Calculate production tracking fields for an order item.

    Returns a dict with:
    - made_to_order (bool)
    - order_type (str): 'made_to_order' or 'rtw'
    - production_duration (Optional[str])
    - estimated_production_days (Optional[int])
    - production_start_date (Optional[datetime])
    - production_due_date (Optional[datetime])
    - working_days_left (Optional[int])
    - is_production_overdue (bool)
    - is_production_completed (bool)
    """
    made_to_order = is_made_to_order_item(item)
    if not made_to_order:
        return {
            "order_type": "rtw",
            "production_duration": None,
            "estimated_production_days": None,
            "production_start_date": None,
            "production_due_date": None,
            "working_days_left": None,
            "is_production_overdue": False,
            "is_production_completed": False,
        }

    # Extract timeline from product if available
    product = item.__dict__.get("product")
    product_timeline: Optional[str] = getattr(product, "made_to_order_timeline", None) if product else None
    pickup_days: Optional[int] = getattr(pickup, "estimated_production_days", None) if pickup else None

    working_days = parse_production_days(product_timeline, pickup_days)

    # Format human-readable configured duration
    production_duration: Optional[str] = None
    if product_timeline and product_timeline.strip():
        production_duration = product_timeline.strip()
    elif working_days is not None:
        production_duration = f"{working_days} working days"

    # Start date from order confirmation, order creation, item creation, or pickup creation
    start_dt: Optional[datetime] = None
    if order is not None:
        start_dt = order.confirmed_at or order.created_at
    if start_dt is None:
        start_dt = item.created_at
    if start_dt is None and pickup is not None:
        start_dt = pickup.created_at

    # Check if item is already completed (ready for pickup)
    ready_at = getattr(pickup, "ready_for_pickup_at", None) if pickup else None
    is_completed = ready_at is not None

    due_dt: Optional[datetime] = None
    working_days_left: Optional[int] = None
    is_overdue = False

    if start_dt is not None and working_days is not None:
        due_date = add_working_days(start_dt, working_days)
        # Combine date with original time and timezone
        tz = start_dt.tzinfo or timezone.utc
        start_time = start_dt.timetz() if start_dt.tzinfo else time(0, 0, tzinfo=timezone.utc)
        due_dt = datetime.combine(due_date, start_time)

        if is_completed:
            working_days_left = 0
            is_overdue = False
        else:
            now_dt = as_of or datetime.now(timezone.utc)
            days_left = count_working_days_between(now_dt, due_date)
            working_days_left = days_left
            is_overdue = days_left < 0

    return {
        "order_type": "made_to_order",
        "production_duration": production_duration,
        "estimated_production_days": working_days,
        "production_start_date": start_dt,
        "production_due_date": due_dt,
        "working_days_left": working_days_left,
        "is_production_overdue": is_overdue,
        "is_production_completed": is_completed,
    }
