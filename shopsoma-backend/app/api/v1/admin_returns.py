"""Admin returns management endpoints"""
from datetime import datetime, date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.dependencies import get_current_admin, get_db
from app.models.order import Order, OrderItem
from app.models.product import Product
from app.models.returns import Return, ReturnStatus
from app.models.user import User
from app.schemas.admin_return import (
    AdminReturnDetail,
    AdminReturnListItem,
    AdminReturnListResponse,
    AdminReturnNotesUpdate,
    AdminReturnStatusUpdate,
    ReturnCustomerInfo,
)

router = APIRouter(prefix="/admin/returns", tags=["Admin Returns"])


@router.get("", response_model=AdminReturnListResponse)
async def list_returns(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: Optional[ReturnStatus] = Query(None, alias="status"),
    search: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    filters = []

    if status_filter:
        filters.append(Return.status == status_filter)

    if search:
        search_term = f"%{search}%"
        filters.append(
            or_(
                Return.return_number.ilike(search_term),
                Order.order_number.ilike(search_term),
                User.email.ilike(search_term),
                User.full_name.ilike(search_term),
            )
        )

    if date_from:
        filters.append(Return.created_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        filters.append(Return.created_at <= datetime.combine(date_to, datetime.max.time()))

    query = (
        select(Return)
        .join(Order, Return.order_id == Order.id)
        .join(User, Return.customer_id == User.id)
        .options(
            selectinload(Return.order),
            selectinload(Return.customer),
            selectinload(Return.order_item),
        )
        .order_by(Return.created_at.desc())
    )

    if filters:
        query = query.where(and_(*filters))

    count_query = select(func.count()).select_from(Return)
    if filters:
        count_query = count_query.join(Order, Return.order_id == Order.id).join(User, Return.customer_id == User.id)
        count_query = count_query.where(and_(*filters))

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    returns = result.scalars().all()

    items = []
    for ret in returns:
        order_item = ret.order_item
        amount = order_item.subtotal if order_item else None
        items.append(
            AdminReturnListItem(
                id=ret.id,
                return_number=ret.return_number,
                status=ret.status,
                reason=ret.reason,
                created_at=ret.created_at,
                order_number=ret.order.order_number if ret.order else None,
                customer=(
                    ReturnCustomerInfo(
                        id=ret.customer.id,
                        full_name=ret.customer.full_name,
                        email=ret.customer.email,
                    )
                    if ret.customer
                    else None
                ),
                product_title=order_item.product_title if order_item else None,
                quantity=order_item.quantity if order_item else None,
                amount=amount,
            )
        )

    total_pages = (total + page_size - 1) // page_size

    return AdminReturnListResponse(
        returns=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/{return_id}", response_model=AdminReturnDetail)
async def get_return_detail(
    return_id: UUID,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Return)
        .where(Return.id == return_id)
        .options(
            selectinload(Return.order),
            selectinload(Return.order_item).selectinload(OrderItem.product).selectinload(Product.images),
            selectinload(Return.customer),
        )
    )
    ret = result.scalar_one_or_none()
    if not ret:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Return not found")

    order_item = ret.order_item
    product_image_url = None
    if order_item and order_item.product and order_item.product.images:
        primary_image = next((img for img in order_item.product.images if img.is_primary), None)
        if not primary_image and order_item.product.images:
            primary_image = order_item.product.images[0]
        product_image_url = primary_image.image_url if primary_image else None

    return AdminReturnDetail(
        id=ret.id,
        return_number=ret.return_number,
        status=ret.status,
        reason=ret.reason,
        description=ret.description,
        opened=(ret.request_details or {}).get("opened"),
        return_action=(ret.request_details or {}).get("return_action"),
        admin_notes=getattr(ret, "admin_notes", None),
        rejection_reason=ret.rejection_reason,
        refund_amount=ret.refund_amount,
        refund_method=ret.refund_method,
        approved_by=ret.approved_by,
        approved_at=ret.approved_at,
        created_at=ret.created_at,
        updated_at=ret.updated_at,
        order_id=ret.order_id,
        order_number=ret.order.order_number if ret.order else None,
        order_date=ret.order.created_at if ret.order else None,
        product_title=order_item.product_title if order_item else None,
        quantity=order_item.quantity if order_item else None,
        amount=order_item.subtotal if order_item else None,
        product_image_url=product_image_url,
    )


@router.patch("/{return_id}/status", response_model=AdminReturnDetail)
async def update_return_status(
    return_id: UUID,
    payload: AdminReturnStatusUpdate,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Return)
        .where(Return.id == return_id)
        .options(
            selectinload(Return.order),
            selectinload(Return.order_item).selectinload(OrderItem.product).selectinload(Product.images),
        )
    )
    ret = result.scalar_one_or_none()
    if not ret:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Return not found")

    ret.status = payload.status
    if payload.admin_notes is not None:
        ret.admin_notes = payload.admin_notes
    if payload.rejection_reason is not None:
        ret.rejection_reason = payload.rejection_reason
    if payload.refund_amount is not None:
        ret.refund_amount = payload.refund_amount
    if payload.refund_method is not None:
        ret.refund_method = payload.refund_method

    if payload.status in {ReturnStatus.APPROVED, ReturnStatus.REJECTED}:
        ret.approved_by = current_admin.id
        ret.approved_at = datetime.utcnow()

    await db.commit()
    await db.refresh(ret)

    return await get_return_detail(return_id, current_admin, db)


@router.patch("/{return_id}/notes", response_model=AdminReturnDetail)
async def update_return_notes(
    return_id: UUID,
    payload: AdminReturnNotesUpdate,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Return).where(Return.id == return_id))
    ret = result.scalar_one_or_none()
    if not ret:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Return not found")

    ret.admin_notes = payload.admin_notes
    await db.commit()

    return await get_return_detail(return_id, current_admin, db)
