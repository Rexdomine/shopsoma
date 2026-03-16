from decimal import Decimal
import uuid

from sqlalchemy import select

from app.models.order import Order, OrderItem
from app.models.payment import Payment, PaymentGateway, TransactionStatus
from app.models.returns import Return
from app.models.user import User, UserRole
from app.models.vendor_pickup import VendorPickup, OrderType


async def test_delete_user_removes_related_order_data(
    client,
    db_session,
    admin_user,
    vendor_user,
    sample_product
):
    customer = User(
        id=uuid.uuid4(),
        email="delete_customer@test.com",
        full_name="Delete Customer",
        role=UserRole.CUSTOMER,
        email_verified=True,
        is_active=True
    )
    db_session.add(customer)
    await db_session.flush()

    order = Order(
        id=uuid.uuid4(),
        order_number=f"ORD-{uuid.uuid4().hex[:8]}",
        customer_id=customer.id,
        subtotal=Decimal("99.99"),
        shipping_cost=Decimal("0.00"),
        tax_amount=Decimal("0.00"),
        discount_amount=Decimal("0.00"),
        total_amount=Decimal("99.99"),
    )
    db_session.add(order)
    await db_session.flush()

    order_item = OrderItem(
        id=uuid.uuid4(),
        order_id=order.id,
        product_id=sample_product.id,
        vendor_id=vendor_user["vendor"].id,
        product_title=sample_product.title,
        unit_price=Decimal("99.99"),
        quantity=1,
        subtotal=Decimal("99.99"),
        commission_rate=Decimal("10.00"),
        commission_amount=Decimal("9.99"),
        vendor_payout=Decimal("89.99"),
    )
    db_session.add(order_item)
    await db_session.flush()

    payment = Payment(
        id=uuid.uuid4(),
        order_id=order.id,
        payment_gateway=PaymentGateway.PAYSTACK,
        amount=Decimal("99.99"),
        currency="NGN",
        status=TransactionStatus.COMPLETED,
    )
    db_session.add(payment)

    return_record = Return(
        id=uuid.uuid4(),
        return_number=f"RET-{uuid.uuid4().hex[:8]}",
        order_id=order.id,
        customer_id=customer.id,
        reason="Damaged item",
    )
    db_session.add(return_record)

    pickup = VendorPickup(
        id=uuid.uuid4(),
        vendor_id=vendor_user["vendor"].id,
        order_id=order.id,
        order_item_id=order_item.id,
        order_type=OrderType.RTW,
    )
    db_session.add(pickup)
    await db_session.commit()

    response = await client.delete(
        f"/api/v1/admin/users/{customer.id}",
        headers=admin_user["headers"],
    )

    assert response.status_code == 200

    orders = (await db_session.execute(
        select(Order).where(Order.customer_id == customer.id)
    )).scalars().all()
    assert len(orders) == 0

    returns = (await db_session.execute(
        select(Return).where(Return.customer_id == customer.id)
    )).scalars().all()
    assert len(returns) == 0

    pickups = (await db_session.execute(
        select(VendorPickup).where(VendorPickup.order_id == order.id)
    )).scalars().all()
    assert len(pickups) == 0

    payments = (await db_session.execute(
        select(Payment).where(Payment.order_id == order.id)
    )).scalars().all()
    assert len(payments) == 0
