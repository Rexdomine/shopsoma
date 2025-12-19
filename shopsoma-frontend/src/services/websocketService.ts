/**
 * WebSocket Service for Real-time Order Updates
 * Connects to backend WebSocket endpoint to receive live order status changes
 */

export type OrderUpdateData = {
  status?: string;
  fulfillment_status: string;
  payment_status: string;
  delivery_provider?: string;
  tracking_number?: string;
  estimated_delivery_date?: string;
  delivered_at?: string;
  cancelled_at?: string;
  updated_at: string;
};

export type WebSocketMessage = {
  type: 'connected' | 'order_update' | 'error' | 'ping';
  order_id?: string;
  current_status?: OrderUpdateData;
  data?: OrderUpdateData;
  message?: string;
};

export type OrderUpdateCallback = (data: OrderUpdateData) => void;

class WebSocketService {
  private ws: WebSocket | null = null;
  private orderId: string | null = null;
  private token: string | null = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelay = 1000; // Start with 1 second
  private callbacks: OrderUpdateCallback[] = [];
  private isConnecting = false;
  private shouldReconnect = true;
  private pingInterval: ReturnType<typeof setInterval> | null = null;

  /**
   * Connect to WebSocket for order updates
   * @param orderId - Order ID to subscribe to
   * @param token - Optional JWT authentication token (required for authenticated users, optional for guests)
   * @param onUpdate - Callback function for order updates
   */
  connect(orderId: string, token: string | null, onUpdate: OrderUpdateCallback): void {
    if (this.isConnecting || (this.ws && this.ws.readyState === WebSocket.OPEN)) {
      console.log('[WebSocket] Already connected or connecting');
      return;
    }

    this.orderId = orderId;
    this.token = token;
    this.shouldReconnect = true;
    this.isConnecting = true;

    // Add callback
    if (!this.callbacks.includes(onUpdate)) {
      this.callbacks.push(onUpdate);
    }

    try {
      // Determine WebSocket protocol based on current page protocol
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';

      // Build WebSocket URL with optional token
      let wsUrl = `${protocol}//${window.location.hostname}:8000/api/v1/ws/orders/${orderId}`;
      if (token) {
        wsUrl += `?token=${token}`;
      }

      const logUrl = token ? wsUrl.replace(token, 'TOKEN_HIDDEN') : wsUrl;
      console.log('[WebSocket] Connecting to:', logUrl, token ? '(authenticated)' : '(guest mode)');
      this.ws = new WebSocket(wsUrl);

      this.ws.onopen = () => {
        console.log('[WebSocket] Connected successfully');
        this.isConnecting = false;
        this.reconnectAttempts = 0;
        this.reconnectDelay = 1000;
        this.startPing();
      };

      this.ws.onmessage = (event) => {
        try {
          const message: WebSocketMessage = JSON.parse(event.data);
          console.log('[WebSocket] Received message:', message.type);

          switch (message.type) {
            case 'connected':
              console.log('[WebSocket] Connection established, initial status:', message.current_status);
              if (message.current_status) {
                this.notifyCallbacks(message.current_status);
              }
              break;

            case 'order_update':
              console.log('[WebSocket] Order update received:', message.data);
              if (message.data) {
                this.notifyCallbacks(message.data);
              }
              break;

            case 'ping':
              // Respond to server ping
              if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                this.ws.send(JSON.stringify({ type: 'pong' }));
              }
              break;

            case 'error':
              console.error('[WebSocket] Server error:', message.message);
              break;

            default:
              console.log('[WebSocket] Unknown message type:', message.type);
          }
        } catch (error) {
          console.error('[WebSocket] Failed to parse message:', error);
        }
      };

      this.ws.onerror = (error) => {
        console.error('[WebSocket] Connection error:', error);
        this.isConnecting = false;
      };

      this.ws.onclose = (event) => {
        console.log('[WebSocket] Connection closed:', event.code, event.reason);
        this.isConnecting = false;
        this.stopPing();

        // Attempt reconnection if not manually closed
        if (this.shouldReconnect && this.reconnectAttempts < this.maxReconnectAttempts) {
          this.reconnectAttempts++;
          const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1); // Exponential backoff
          console.log(`[WebSocket] Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`);

          setTimeout(() => {
            if (this.shouldReconnect && this.orderId) {
              // Reconnect with token (or null for guest mode)
              this.connect(this.orderId, this.token, this.callbacks[0]);
            }
          }, delay);
        } else if (this.reconnectAttempts >= this.maxReconnectAttempts) {
          console.error('[WebSocket] Max reconnection attempts reached');
        }
      };
    } catch (error) {
      console.error('[WebSocket] Failed to create connection:', error);
      this.isConnecting = false;
    }
  }

  /**
   * Disconnect from WebSocket
   */
  disconnect(): void {
    console.log('[WebSocket] Disconnecting...');
    this.shouldReconnect = false;
    this.stopPing();

    if (this.ws) {
      this.ws.close(1000, 'Client disconnect');
      this.ws = null;
    }

    this.callbacks = [];
    this.orderId = null;
    this.token = null;
    this.reconnectAttempts = 0;
  }

  /**
   * Check if WebSocket is connected
   */
  isConnected(): boolean {
    return this.ws !== null && this.ws.readyState === WebSocket.OPEN;
  }

  /**
   * Notify all registered callbacks
   */
  private notifyCallbacks(data: OrderUpdateData): void {
    this.callbacks.forEach(callback => {
      try {
        callback(data);
      } catch (error) {
        console.error('[WebSocket] Callback error:', error);
      }
    });
  }

  /**
   * Start periodic ping to keep connection alive
   */
  private startPing(): void {
    this.stopPing();
    this.pingInterval = setInterval(() => {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify({ type: 'ping' }));
      }
    }, 30000); // Ping every 30 seconds
  }

  /**
   * Stop periodic ping
   */
  private stopPing(): void {
    if (this.pingInterval) {
      clearInterval(this.pingInterval);
      this.pingInterval = null;
    }
  }

  /**
   * Add additional callback for order updates
   */
  addCallback(callback: OrderUpdateCallback): void {
    if (!this.callbacks.includes(callback)) {
      this.callbacks.push(callback);
    }
  }

  /**
   * Remove callback
   */
  removeCallback(callback: OrderUpdateCallback): void {
    this.callbacks = this.callbacks.filter(cb => cb !== callback);
  }
}

// Singleton instance
const websocketService = new WebSocketService();
export default websocketService;
