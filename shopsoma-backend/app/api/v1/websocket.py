"""
WebSocket endpoints for real-time updates
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
import logging

from app.core.database import get_db
from app.models.order import Order
from app.models.order_guest_capability import OrderCurrentOwner
from app.services.websocket_manager import get_connection_manager
from app.api.dependencies import get_current_user_from_token


logger = logging.getLogger(__name__)

router = APIRouter(tags=["WebSocket"])


@router.websocket("/ws/orders/{order_id}")
async def websocket_order_updates(
    websocket: WebSocket,
    order_id: UUID,
    token: str = Query(None, description="Optional JWT access token for authenticated users"),
    db: AsyncSession = Depends(get_db)
):
    """
    WebSocket endpoint for real-time order updates

    Customers connect to this endpoint to receive live updates about their order status.

    Supports TWO authentication modes:
    1. Authenticated: ws://localhost:8000/api/v1/ws/orders/{order_id}?token={jwt_token}
       - For logged-in users
       - Verifies user owns the order

    2. Guest: not supported. Guest tracking uses the capability-protected
       REST endpoint and bounded polling; capabilities must never be put in a
       WebSocket URL.

    Messages sent to client:
    {
        "type": "order_update",
        "order_id": "uuid",
        "data": {
            "status": "processing",
            "fulfillment_status": "pending",
            "payment_status": "paid",
            "updated_at": "2025-12-18T10:00:00Z"
        }
    }
    """
    manager = get_connection_manager()
    user = None
    is_authenticated = False

    try:
        # Attempt authentication if token provided
        if token:
            try:
                user = await get_current_user_from_token(token, db)
                is_authenticated = True
                logger.info(f"[WebSocket] Authenticated user {user.email} connecting to order {order_id}")
            except Exception as e:
                logger.warning(f"[WebSocket] Token authentication failed: {str(e)}")
                await websocket.close(code=1008, reason="Authentication required")
                return
        else:
            await websocket.close(code=1008, reason="Authentication required")
            return

        # Verify order exists
        order_query = select(Order).where(Order.id == order_id)
        result = await db.execute(order_query)
        order = result.scalar_one_or_none()

        if not order:
            logger.warning(f"[WebSocket] Order {order_id} not found")
            await websocket.close(code=1008, reason="Order not found")
            return

        # Authenticated sockets are limited to the canonical current owner.
        # A claimed guest order retains its original customer_id, while
        # OrderCurrentOwner records the account that now owns the order.
        owner_result = await db.execute(
            select(OrderCurrentOwner).where(OrderCurrentOwner.order_id == order_id)
        )
        current_owner = owner_result.scalar_one_or_none()
        canonical_owner_id = (
            current_owner.current_authenticated_user_id
            if current_owner and current_owner.current_authenticated_user_id
            else current_owner.original_customer_id if current_owner else order.customer_id
        )
        if canonical_owner_id != user.id:
            logger.warning(f"[WebSocket] User {user.id} does not own order {order_id}")
            await websocket.close(code=1008, reason="Unauthorized")
            return

        # Accept connection
        await manager.connect(websocket, str(order_id))

        # Send initial order state
        await websocket.send_json({
            "type": "connected",
            "message": f"Connected to order {order_id} updates",
            "order_id": str(order_id),
            "current_status": {
                "status": order.status.value,
                "fulfillment_status": order.fulfillment_status.value if order.fulfillment_status else None,
                "payment_status": order.payment_status.value,
                "updated_at": order.updated_at.isoformat()
            }
        })

        # Log connection type
        connection_type = "authenticated" if is_authenticated else "guest"
        user_info = f"user {user.email}" if user else "guest"
        logger.info(f"[WebSocket] {user_info} connected to order {order_id} ({connection_type} mode)")

        # Keep connection alive and handle incoming messages
        while True:
            try:
                # Receive messages from client (heartbeat, ping, etc.)
                data = await websocket.receive_text()

                # Handle ping/pong for keep-alive
                if data == "ping":
                    await websocket.send_json({"type": "pong"})

            except WebSocketDisconnect:
                logger.info(f"[WebSocket] Client disconnected from order {order_id}")
                break
            except Exception as e:
                logger.error(f"[WebSocket] Error receiving message: {str(e)}")
                break

    except Exception as e:
        logger.error(f"[WebSocket] Error in websocket connection: {str(e)}", exc_info=True)

    finally:
        manager.disconnect(websocket)


@router.get("/ws/health")
async def websocket_health():
    """
    WebSocket health check endpoint
    Returns the number of active connections
    """
    manager = get_connection_manager()
    return {
        "status": "healthy",
        "active_connections": manager.get_connection_count(),
        "orders_tracked": len(manager.order_connections)
    }
