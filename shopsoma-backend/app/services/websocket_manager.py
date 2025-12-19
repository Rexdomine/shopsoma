"""
WebSocket Manager for Real-time Order Updates
Manages WebSocket connections and broadcasts order status changes to customers
"""
import logging
from typing import Dict, Set
from fastapi import WebSocket
from uuid import UUID
import json

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections for real-time updates"""

    def __init__(self):
        # Maps order_id -> set of websocket connections
        self.order_connections: Dict[str, Set[WebSocket]] = {}
        # Maps websocket -> order_id for cleanup
        self.connection_orders: Dict[WebSocket, str] = {}

    async def connect(self, websocket: WebSocket, order_id: str):
        """Accept a new WebSocket connection for an order"""
        await websocket.accept()

        # Add to order connections
        if order_id not in self.order_connections:
            self.order_connections[order_id] = set()

        self.order_connections[order_id].add(websocket)
        self.connection_orders[websocket] = order_id

        logger.info(f"[WebSocket] New connection for order {order_id}. Total connections: {len(self.order_connections[order_id])}")

    def disconnect(self, websocket: WebSocket):
        """Remove a WebSocket connection"""
        if websocket in self.connection_orders:
            order_id = self.connection_orders[websocket]

            # Remove from order connections
            if order_id in self.order_connections:
                self.order_connections[order_id].discard(websocket)

                # Clean up empty sets
                if not self.order_connections[order_id]:
                    del self.order_connections[order_id]

            # Remove from connection mapping
            del self.connection_orders[websocket]

            logger.info(f"[WebSocket] Connection closed for order {order_id}")

    async def send_order_update(self, order_id: str, data: dict):
        """
        Send order update to all connected clients for a specific order

        Args:
            order_id: UUID of the order
            data: Update data to send (order status, tracking info, etc.)
        """
        order_id_str = str(order_id)

        if order_id_str not in self.order_connections:
            logger.debug(f"[WebSocket] No active connections for order {order_id_str}")
            return

        # Prepare message
        message = {
            "type": "order_update",
            "order_id": order_id_str,
            "data": data
        }

        # Send to all connected clients for this order
        disconnected = []
        connections = self.order_connections[order_id_str].copy()

        for connection in connections:
            try:
                await connection.send_json(message)
                logger.debug(f"[WebSocket] Sent update to client for order {order_id_str}")
            except Exception as e:
                logger.error(f"[WebSocket] Failed to send to client: {str(e)}")
                disconnected.append(connection)

        # Clean up disconnected clients
        for connection in disconnected:
            self.disconnect(connection)

    async def broadcast_to_all(self, data: dict):
        """
        Broadcast a message to all connected clients (use sparingly)

        Args:
            data: Message data to broadcast
        """
        message = {
            "type": "broadcast",
            "data": data
        }

        all_connections = set(self.connection_orders.keys())
        logger.info(f"[WebSocket] Broadcasting to {len(all_connections)} connections")

        disconnected = []
        for connection in all_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"[WebSocket] Failed to broadcast: {str(e)}")
                disconnected.append(connection)

        # Clean up disconnected clients
        for connection in disconnected:
            self.disconnect(connection)

    def get_connection_count(self, order_id: str = None) -> int:
        """Get number of active connections"""
        if order_id:
            return len(self.order_connections.get(str(order_id), set()))
        return len(self.connection_orders)


# Singleton instance
manager = ConnectionManager()


def get_connection_manager() -> ConnectionManager:
    """Get the global connection manager instance"""
    return manager
