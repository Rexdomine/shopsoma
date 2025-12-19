import { useEffect, useMemo, useState } from 'react';
import { Link, useParams, useNavigate } from 'react-router-dom';
import { ROUTES } from '../../config/constants';
import {
  orderService,
  type OrderTracking,
  type OrderStatus,
  buildMockTracking,
} from '../../services/orderService';
import { checkoutService } from '../../services/checkoutService';
import websocketService, { type OrderUpdateData } from '../../services/websocketService';

const STATUS_STEPS: Array<{ key: OrderStatus; label: string }> = [
  { key: 'order_placed', label: 'Order Placed' },
  { key: 'in_transit', label: 'In Transit' },
  { key: 'out_for_delivery', label: 'Out for Delivery' },
  { key: 'delivered', label: 'Delivered' },
];

// Terminal states (not shown in progress bar)
const TERMINAL_STATES: Record<OrderStatus, { label: string; color: string }> = {
  'delivery_failed': { label: 'Delivery Failed', color: 'red' },
  'returned': { label: 'Returned', color: 'orange' },
  'cancelled': { label: 'Cancelled', color: 'gray' },
  // Include normal states for type safety
  'order_placed': { label: 'Order Placed', color: 'yellow' },
  'pending_confirmation': { label: 'Pending Confirmation', color: 'yellow' },
  'in_transit': { label: 'In Transit', color: 'blue' },
  'out_for_delivery': { label: 'Out for Delivery', color: 'blue' },
  'delivered': { label: 'Delivered', color: 'green' },
};

const formatDisplayDate = (value: string) => {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString('en-GB', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  });
};

export default function OrderTracking() {
  const navigate = useNavigate();
  const { orderId } = useParams<{ orderId: string }>();
  const [tracking, setTracking] = useState<OrderTracking | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [showOrderModal, setShowOrderModal] = useState(false);
  const [orderDetails, setOrderDetails] = useState<any>(null);
  const [loadingOrder, setLoadingOrder] = useState(false);
  const [isConnectedToWebSocket, setIsConnectedToWebSocket] = useState(false);
  const [wsError, setWsError] = useState<string | null>(null);

  // Initial load of tracking data
  useEffect(() => {
    if (!orderId) {
      setError('Order ID is missing');
      setLoading(false);
      return;
    }

    let isMounted = true;
    (async () => {
      try {
        const data = await orderService.getOrderTracking(orderId);
        if (isMounted) {
          setTracking(data);
          setError(null);
        }
      } catch (err) {
        console.error('Failed to fetch tracking details', err);
        if (isMounted) {
          setError('Unable to fetch live tracking details. Showing latest available information.');
          setTracking(buildMockTracking(orderId));
        }
      } finally {
        if (isMounted) {
          setLoading(false);
        }
      }
    })();

    return () => {
      isMounted = false;
    };
  }, [orderId]);

  // WebSocket connection for real-time updates
  useEffect(() => {
    if (!orderId) return;

    // Get JWT token from localStorage (optional for guest users)
    const token = localStorage.getItem('token');

    if (token) {
      console.log('[OrderTracking] Connecting to WebSocket with authentication for order:', orderId);
    } else {
      console.log('[OrderTracking] Connecting to WebSocket in guest mode for order:', orderId);
    }

    setIsConnectedToWebSocket(true);

    // Handle real-time order updates
    const handleOrderUpdate = (data: OrderUpdateData) => {
      console.log('[OrderTracking] ===== WEBSOCKET UPDATE RECEIVED =====');
      console.log('[OrderTracking] Raw data:', JSON.stringify(data, null, 2));
      console.log('[OrderTracking] Fulfillment status:', data.fulfillment_status);

      setTracking((prevTracking) => {
        if (!prevTracking) {
          console.warn('[OrderTracking] No previous tracking data, cannot update');
          return prevTracking;
        }

        console.log('[OrderTracking] Previous status:', prevTracking.current_status);

        // Map fulfillment_status to current_status for the UI
        let currentStatus: OrderStatus = prevTracking.current_status;

        // Map backend fulfillment statuses to frontend OrderStatus
        const fulfillmentStatus = data.fulfillment_status?.toLowerCase();

        // Handle order lifecycle statuses
        if (fulfillmentStatus === 'order_received') {
          currentStatus = 'order_placed';
        } else if (
          fulfillmentStatus === 'preparing_for_pickup' ||
          fulfillmentStatus === 'pickup_scheduled' ||
          fulfillmentStatus === 'picked_up' ||
          fulfillmentStatus === 'in_transit'
        ) {
          currentStatus = 'in_transit';
        } else if (fulfillmentStatus === 'out_for_delivery') {
          currentStatus = 'out_for_delivery';
        } else if (fulfillmentStatus === 'delivered') {
          currentStatus = 'delivered';
        }
        // Handle terminal/failure states
        else if (fulfillmentStatus === 'delivery_failed') {
          currentStatus = 'delivery_failed';
        } else if (fulfillmentStatus === 'returned') {
          currentStatus = 'returned';
        } else if (fulfillmentStatus === 'cancelled') {
          currentStatus = 'cancelled';
        } else {
          console.warn('[OrderTracking] Unknown fulfillment status:', data.fulfillment_status);
        }

        console.log('[OrderTracking] Mapped status:', fulfillmentStatus, '→', currentStatus);

        const updatedTracking = {
          ...prevTracking,
          current_status: currentStatus,
          tracking_id: data.tracking_number || prevTracking.tracking_id,
          updated_at: data.updated_at,
          delivery_provider: data.delivery_provider,
        };

        console.log('[OrderTracking] Updated tracking:', JSON.stringify(updatedTracking, null, 2));
        console.log('[OrderTracking] ===== UPDATE COMPLETE =====');

        return updatedTracking;
      });
    };

    // Connect to WebSocket
    try {
      websocketService.connect(orderId, token, handleOrderUpdate);
      setWsError(null);
      console.log('[OrderTracking] WebSocket connection initiated');
    } catch (error) {
      console.error('[OrderTracking] WebSocket connection error:', error);
      setWsError('WebSocket connection failed');
      setIsConnectedToWebSocket(false);
    }

    // Fallback: Poll for updates every 10 seconds if WebSocket isn't connected
    const pollInterval = setInterval(async () => {
      if (!websocketService.isConnected()) {
        console.log('[OrderTracking] WebSocket not connected, polling for updates...');
        try {
          const data = await orderService.getOrderTracking(orderId);
          console.log('[OrderTracking] Polling update received:', data);
          setTracking(data);
        } catch (err) {
          console.error('[OrderTracking] Polling error:', err);
        }
      }
    }, 10000); // Poll every 10 seconds

    // Cleanup on unmount
    return () => {
      console.log('[OrderTracking] Disconnecting WebSocket and clearing poll interval');
      websocketService.disconnect();
      clearInterval(pollInterval);
      setIsConnectedToWebSocket(false);
    };
  }, [orderId]);

  const activeIndex = useMemo(() => {
    if (!tracking) return 0;
    const index = STATUS_STEPS.findIndex((step) => step.key === tracking.current_status);
    return index >= 0 ? index : 0;
  }, [tracking]);

  // Check if order is in a terminal state (failed/returned/cancelled)
  const isTerminalState = useMemo(() => {
    if (!tracking) return false;
    return ['delivery_failed', 'returned', 'cancelled'].includes(tracking.current_status);
  }, [tracking]);

  const handleViewOrderDetails = async () => {
    if (!orderId) return;

    setLoadingOrder(true);
    try {
      const order = await checkoutService.getOrder(orderId);
      setOrderDetails(order);
      setShowOrderModal(true);
    } catch (err) {
      console.error('Error loading order details:', err);
      alert('Unable to load order details');
    } finally {
      setLoadingOrder(false);
    }
  };

  if (!orderId) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-sm text-gray-600">Order ID is required to track your order.</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-white flex flex-col">
      <div className="px-8 py-6 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Link
            to={ROUTES.HOME}
            className="text-4xl text-primary"
            style={{ fontFamily: 'Lao MN, var(--font-display, serif)' }}
            aria-label="Shopsoma home"
          >
            S
          </Link>
          <button
            onClick={() => navigate(-1)}
            className="text-sm text-gray-600 hover:text-primary transition flex items-center gap-1"
          >
            <span>←</span>
            <span>Back</span>
          </button>
        </div>
        <span className="text-xs uppercase tracking-[0.3em] text-gray-500">Track My Order</span>
      </div>

      <div className="flex-1 px-4 sm:px-8 pb-16">
        <div className="max-w-5xl mx-auto space-y-8">
          {error && (
            <div className="rounded-sm bg-amber-50 border border-amber-200 text-amber-700 text-sm px-4 py-2">
              {error}
            </div>
          )}

          <div className="rounded-sm border border-gray-100 bg-gray-50 px-6 py-5">
            <div className="flex items-center justify-between">
              <p className="text-sm font-semibold text-gray-800">
                Tracking ID{' '}
                <span className="text-primary">
                  {tracking?.tracking_id || 'Loading...'}
                </span>
              </p>
              {isConnectedToWebSocket && !wsError && (
                <div className="flex items-center gap-2 text-xs text-emerald-600">
                  <span className="relative flex h-2 w-2">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
                  </span>
                  <span>Live Updates Active</span>
                </div>
              )}
              {wsError && (
                <div className="flex items-center gap-2 text-xs text-amber-600">
                  <span className="relative flex h-2 w-2">
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-amber-500"></span>
                  </span>
                  <span>Polling for Updates</span>
                </div>
              )}
            </div>
          </div>

          <div className="bg-white border border-gray-100 rounded-sm px-6 py-8 shadow-sm space-y-8">
            {loading ? (
              <div className="text-center text-sm text-gray-500">Fetching latest tracking updates...</div>
            ) : (
              <>
                {/* Terminal State Alert Banner */}
                {isTerminalState && tracking && (
                  <div
                    className={`rounded-sm px-6 py-4 border-2 ${
                      tracking.current_status === 'cancelled'
                        ? 'bg-gray-50 border-gray-300 text-gray-700'
                        : tracking.current_status === 'returned'
                        ? 'bg-orange-50 border-orange-300 text-orange-700'
                        : 'bg-red-50 border-red-300 text-red-700'
                    }`}
                  >
                    <div className="flex items-center gap-3">
                      <span className="text-2xl">
                        {tracking.current_status === 'cancelled' && '❌'}
                        {tracking.current_status === 'returned' && '↩️'}
                        {tracking.current_status === 'delivery_failed' && '⚠️'}
                      </span>
                      <div>
                        <p className="font-semibold text-sm">
                          {TERMINAL_STATES[tracking.current_status]?.label || 'Status Update'}
                        </p>
                        <p className="text-xs mt-1">
                          {tracking.current_status === 'cancelled' && 'This order has been cancelled.'}
                          {tracking.current_status === 'returned' && 'This order has been returned.'}
                          {tracking.current_status === 'delivery_failed' && 'Delivery attempt was unsuccessful. We will contact you shortly.'}
                        </p>
                      </div>
                    </div>
                  </div>
                )}

                <div className="space-y-6">
                  <div className="flex flex-col gap-6">
                    <div className="flex items-center justify-between">
                      {STATUS_STEPS.map((step, index) => {
                        const isActive = index <= activeIndex;
                        return (
                          <div key={step.key} className="flex-1 flex flex-col items-center text-center">
                            <div className="flex items-center w-full">
                              {index > 0 && (
                                <span
                                  className={`flex-1 h-px ${
                                    index <= activeIndex ? 'bg-primary' : 'bg-gray-200'
                                  }`}
                                />
                              )}
                              <span
                                className={`w-9 h-9 rounded-full border-2 flex items-center justify-center ${
                                  isActive ? 'border-primary bg-primary/10 text-primary' : 'border-gray-200 text-gray-400'
                                }`}
                              >
                                <span className="text-xs font-semibold">{index + 1}</span>
                              </span>
                              {index < STATUS_STEPS.length - 1 && (
                                <span
                                  className={`flex-1 h-px ${
                                    index < activeIndex ? 'bg-primary' : 'bg-gray-200'
                                  }`}
                                />
                              )}
                            </div>
                            <p className="mt-2 text-xs text-gray-600 leading-tight">{step.label}</p>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </div>

                <div className="space-y-2">
                  <p className="text-xs uppercase tracking-[0.2em] text-gray-400">Last Updated Date</p>
                  <p className="text-sm text-gray-700">
                    {tracking ? formatDisplayDate(tracking.updated_at) : '—'}
                  </p>
                </div>

                <div className="space-y-3">
                  <p className="text-xs uppercase tracking-[0.2em] text-gray-400">Tracking Details</p>
                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-sm">
                      <thead>
                        <tr className="bg-gray-50 text-gray-500 uppercase text-xs tracking-[0.2em]">
                          <th className="py-3 px-4 font-medium">S/N</th>
                          <th className="py-3 px-4 font-medium">Order ID</th>
                          <th className="py-3 px-4 font-medium">Tracking No.</th>
                          <th className="py-3 px-4 font-medium">Date</th>
                          <th className="py-3 px-4 font-medium">Amount</th>
                          <th className="py-3 px-4 font-medium">Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr className="border-b border-gray-100">
                          <td className="py-3 px-4 text-gray-700">1.</td>
                          <td className="py-3 px-4">
                            <button
                              onClick={handleViewOrderDetails}
                              disabled={loadingOrder}
                              className="text-primary hover:underline font-semibold disabled:opacity-50"
                            >
                              {tracking?.order_number || orderId}
                            </button>
                          </td>
                          <td className="py-3 px-4 text-gray-700">{tracking?.tracking_id || '—'}</td>
                          <td className="py-3 px-4 text-gray-700">
                            {tracking
                              ? formatDisplayDate(tracking.history?.[0]?.occurred_at || tracking.updated_at)
                              : '—'}
                          </td>
                          <td className="py-3 px-4 text-gray-700">
                            {tracking
                              ? new Intl.NumberFormat('en-NG', {
                                  style: 'currency',
                                  currency: tracking.currency || 'NGN',
                                  maximumFractionDigits: 0,
                                }).format(tracking.amount || 0)
                              : '—'}
                          </td>
                          <td className="py-3 px-4">
                            <span
                              className={`inline-flex px-3 py-1 rounded-full text-xs font-semibold ${
                                isTerminalState
                                  ? tracking?.current_status === 'cancelled'
                                    ? 'bg-gray-100 text-gray-700'
                                    : tracking?.current_status === 'returned'
                                    ? 'bg-orange-50 text-orange-700'
                                    : 'bg-red-50 text-red-700'
                                  : activeIndex >= STATUS_STEPS.length - 1
                                  ? 'bg-emerald-50 text-emerald-700'
                                  : activeIndex > 1
                                  ? 'bg-primary/10 text-primary'
                                  : 'bg-amber-50 text-amber-700'
                              }`}
                            >
                              {tracking
                                ? TERMINAL_STATES[tracking.current_status]?.label ||
                                  STATUS_STEPS.find((step) => step.key === tracking.current_status)?.label ||
                                  'Processing'
                                : 'Processing'}
                            </span>
                          </td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </div>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Order Details Modal */}
      {showOrderModal && orderDetails && (
        <div className="fixed inset-0 bg-black/30 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-sm max-w-2xl w-full max-h-[90vh] overflow-y-auto shadow-xl">
            <div className="sticky top-0 bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between">
              <h2 className="text-lg font-semibold text-dark">Order Details</h2>
              <button
                onClick={() => setShowOrderModal(false)}
                className="text-gray-400 hover:text-gray-600 text-2xl"
              >
                ×
              </button>
            </div>

            <div className="p-6 space-y-6">
              {/* Order Info */}
              <div className="space-y-2">
                <div className="flex justify-between text-sm">
                  <span className="text-gray-600">Order Number:</span>
                  <span className="font-semibold">{orderDetails.order_number}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-600">Order Date:</span>
                  <span className="font-semibold">
                    {new Date(orderDetails.created_at).toLocaleDateString('en-US', {
                      year: 'numeric',
                      month: 'long',
                      day: 'numeric',
                    })}
                  </span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-600">Payment Status:</span>
                  <span className={`font-semibold uppercase ${
                    orderDetails.payment_status === 'paid'
                      ? 'text-green-600'
                      : orderDetails.payment_status === 'failed'
                      ? 'text-red-600'
                      : 'text-yellow-600'
                  }`}>
                    {orderDetails.payment_status}
                  </span>
                </div>
              </div>

              {/* Order Items */}
              <div>
                <h3 className="text-sm font-semibold text-gray-700 uppercase tracking-[0.2em] mb-3">
                  Items ({orderDetails.items?.length || 0})
                </h3>
                <div className="space-y-3">
                  {orderDetails.items?.map((item: any, index: number) => (
                    <div key={index} className="flex gap-3 border-b border-gray-100 pb-3">
                      {/* Product Image */}
                      {item.product_image_url && (
                        <div className="flex-shrink-0">
                          <img
                            src={item.product_image_url}
                            alt={item.product_title}
                            className="w-16 h-16 object-cover rounded-sm border border-gray-200"
                          />
                        </div>
                      )}

                      {/* Product Details */}
                      <div className="flex-1 min-w-0">
                        <p className="font-medium text-sm">{item.product_title}</p>
                        {item.variant_details && (
                          <p className="text-xs text-gray-500 mt-1">
                            {item.variant_details.size && `Size: ${item.variant_details.size}`}
                            {item.variant_details.color && ` • Color: ${item.variant_details.color}`}
                          </p>
                        )}
                        <p className="text-xs text-gray-500 mt-1">Qty: {item.quantity}</p>
                      </div>

                      {/* Price */}
                      <div className="text-right flex-shrink-0">
                        <p className="font-semibold text-sm">₦{item.subtotal.toLocaleString()}</p>
                        <p className="text-xs text-gray-500">₦{item.unit_price.toLocaleString()} each</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Order Summary */}
              <div className="border-t border-gray-200 pt-4 space-y-2">
                <div className="flex justify-between text-sm">
                  <span className="text-gray-600">Subtotal:</span>
                  <span>₦{orderDetails.subtotal.toLocaleString()}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-600">Shipping:</span>
                  <span>₦{orderDetails.shipping_cost.toLocaleString()}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-600">Tax:</span>
                  <span>₦{orderDetails.tax_amount.toLocaleString()}</span>
                </div>
                {orderDetails.discount_amount > 0 && (
                  <div className="flex justify-between text-sm text-green-600">
                    <span>Discount:</span>
                    <span>-₦{orderDetails.discount_amount.toLocaleString()}</span>
                  </div>
                )}
                <div className="flex justify-between text-base font-bold border-t border-gray-200 pt-2 mt-2">
                  <span>Total:</span>
                  <span>₦{orderDetails.total_amount.toLocaleString()}</span>
                </div>
              </div>

              {/* Close Button */}
              <button
                onClick={() => setShowOrderModal(false)}
                className="w-full rounded-sm bg-gray-100 text-gray-700 font-semibold py-3 text-sm hover:bg-gray-200 transition"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
