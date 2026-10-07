import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useParams, useNavigate } from 'react-router-dom';
import { ROUTES, STORAGE_KEYS } from '../../config/constants';
import {
  orderService,
  type OrderTracking,
  type OrderStatus,
} from '../../services/orderService';
import { checkoutService } from '../../services/checkoutService';
import { paymentService, buildPaystackWidgetConfig } from '../../services/paymentService';
import websocketService, { type OrderUpdateData } from '../../services/websocketService';
import { useCurrencyStore } from '../../store/currencyStore';
import { formatPriceWithConversion, type Currency } from '../../utils/pricing';
import { loadCheckoutCapability } from '../../utils/checkoutCapability';

const STATUS_STEPS: Array<{ key: OrderStatus; label: string }> = [
  { key: 'order_placed', label: 'Order Placed' },
  { key: 'picked_up', label: 'Picked Up' },
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
  'picked_up': { label: 'Picked Up', color: 'indigo' },
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
  const detailRequestGeneration = useRef(0);
  const pollingGeneration = useRef(0);
  const exchangeRates = useCurrencyStore((state) => state.exchangeRates);
  const resolvedOrderId = tracking?.order_id ?? orderId;
  const orderCurrency = (orderDetails?.currency || 'NGN') as Currency;
  const formatOrderPrice = (amount: number) =>
    formatPriceWithConversion(amount, 'NGN', orderCurrency, exchangeRates);

  // Never let data loaded for the previous route drive the next order's UI.
  useEffect(() => {
    detailRequestGeneration.current += 1;
    setTracking(null);
    setOrderDetails(null);
    setShowOrderModal(false);
    setLoadingOrder(false);
    setLoading(true);
  }, [orderId]);

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
        const data = await orderService.getOrderTracking(orderId, loadCheckoutCapability(orderId));
        if (isMounted) {
          setTracking(data);
          setError(null);
        }
      } catch (err) {
        console.error('Failed to fetch tracking details', err);
        if (isMounted) {
          setError('Tracking information is unavailable. Please try again later.');
          // Never replace an authorized response with fabricated order data.
          setTracking(null);
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

    const requestGeneration = ++pollingGeneration.current;
    let isPollingEffectActive = true;
    let latestPollSequence = 0;
    let latestSettledPollSequence = 0;
    const pollingOrderId = tracking?.order_id;
    // Get JWT token from localStorage (optional for guest users)
    const token = localStorage.getItem(STORAGE_KEYS.ACCESS_TOKEN);

    if (token && tracking?.order_id) {
      console.log('[OrderTracking] Connecting to WebSocket with authentication for order:', tracking.order_id);
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
          fulfillmentStatus === 'pickup_scheduled'
        ) {
          currentStatus = 'order_placed';
        } else if (fulfillmentStatus === 'picked_up') {
          currentStatus = 'picked_up';
        } else if (fulfillmentStatus === 'in_transit') {
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

    // Guest capabilities are header-only and cannot be sent by the browser
    // WebSocket API without putting them in the URL. Use protected REST
    // polling for guests; only authenticated users open a JWT socket.
    if (token && tracking?.order_id) {
      try {
        websocketService.connect(tracking.order_id, token, handleOrderUpdate);
        setWsError(null);
        console.log('[OrderTracking] WebSocket connection initiated');
      } catch (error) {
        console.error('[OrderTracking] WebSocket connection error:', error);
        setWsError('WebSocket connection failed');
        setIsConnectedToWebSocket(false);
      }
    } else {
      setWsError('Guest tracking uses protected polling');
      setIsConnectedToWebSocket(false);
    }

    // Fallback: Poll for updates every 10 seconds if WebSocket isn't connected
    const pollInterval = setInterval(async () => {
      const pollSequence = ++latestPollSequence;
      if (!websocketService.isConnected()) {
        console.log('[OrderTracking] WebSocket not connected, polling for updates...');
        try {
          const data = await orderService.getOrderTracking(orderId, loadCheckoutCapability(orderId));
          console.log('[OrderTracking] Polling update received:', data);
          if (
            isPollingEffectActive &&
            requestGeneration === pollingGeneration.current &&
            pollSequence >= latestSettledPollSequence &&
            data.order_id &&
            (data.order_id === orderId || data.order_id === pollingOrderId || !pollingOrderId)
          ) {
            latestSettledPollSequence = pollSequence;
            setTracking(data);
            setError(null);
            setLoading(false);
          }
        } catch (err) {
          console.error('[OrderTracking] Polling error:', err);
          const status = (err as { response?: { status?: number } })?.response?.status;
          if (
            isPollingEffectActive &&
            requestGeneration === pollingGeneration.current &&
            pollSequence >= latestSettledPollSequence &&
            [401, 403, 404, 410].includes(status ?? 0)
          ) {
            latestSettledPollSequence = pollSequence;
            setTracking(null);
            setError('Tracking information is unavailable. Please try again later.');
          }
        }
      }
    }, 10000); // Poll every 10 seconds

    // Cleanup on unmount
    return () => {
      isPollingEffectActive = false;
      console.log('[OrderTracking] Disconnecting WebSocket and clearing poll interval');
      websocketService.disconnect();
      clearInterval(pollInterval);
      setIsConnectedToWebSocket(false);
    };
  }, [orderId, tracking?.order_id]);

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

  const isPaymentPending = useMemo(() => {
    if (!tracking) return false;
    const ps = tracking.payment_status?.toLowerCase();
    return ps === 'pending' || ps === 'unpaid' || ps === 'failed';
  }, [tracking]);

  const [isRetryingPayment, setIsRetryingPayment] = useState(false);
  const [isCancellingOrder, setIsCancellingOrder] = useState(false);

  const handleRetryPayment = async () => {
    if (!resolvedOrderId) return;
    setIsRetryingPayment(true);
    try {
      let order = orderDetails;
      if (!order) {
        order = await checkoutService.getOrder(
          resolvedOrderId,
          loadCheckoutCapability(resolvedOrderId),
        );
        setOrderDetails(order);
      }
      const email = order?.customer_email || order?.customer?.email || 'guest@shopsoma.com';
      const paymentData = await paymentService.initializePayment({
        order_id: resolvedOrderId,
        email,
        payment_gateway: 'paystack',
        currency: (order?.currency as any) || 'NGN',
        callback_url: `${window.location.origin}/payment/verify`,
      }, loadCheckoutCapability(resolvedOrderId));

      if (paymentData.authorization_url && (window as any).PaystackPop) {
        const widgetTruth = buildPaystackWidgetConfig(paymentData, {
          key: import.meta.env.VITE_PAYSTACK_PUBLIC_KEY,
          email,
        });
        const handler = (window as any).PaystackPop.setup({
          ...widgetTruth,
          callback: (response: { reference: string }) => {
            paymentService.verifyPayment({
              reference: response.reference,
              payment_gateway: 'paystack',
            }).then(() => {
              window.location.href = `${ROUTES.ORDER_SUCCESS}?orderId=${resolvedOrderId}&payment=success`;
            }).catch((err) => {
              console.error('Verification error:', err);
              window.location.href = `${ROUTES.ORDER_SUCCESS}?orderId=${resolvedOrderId}&payment=verification_failed`;
            });
          },
          onClose: () => {
            setIsRetryingPayment(false);
          },
        });
        handler.openIframe();
      } else if (paymentData.authorization_url) {
        window.location.href = paymentData.authorization_url;
      }
    } catch (err: any) {
      console.error('Failed to initialize payment:', err);
      const detail = err.response?.data?.detail;
      const msg = typeof detail === 'string' ? detail : detail?.message || err.message || 'Unable to re-initialize payment.';
      alert(msg);
      setIsRetryingPayment(false);
    }
  };

  const handleCancelOrder = async () => {
    if (!resolvedOrderId) return;
    if (!window.confirm('Are you sure you want to cancel this order?')) return;
    setIsCancellingOrder(true);
    try {
      await checkoutService.cancelOrder(
        resolvedOrderId,
        'Customer cancelled unpaid order',
        loadCheckoutCapability(resolvedOrderId),
      );
      const updated = await orderService.getOrderTracking(
        resolvedOrderId,
        loadCheckoutCapability(resolvedOrderId),
      );
      setTracking(updated);
      alert('Order has been cancelled.');
    } catch (err: any) {
      console.error('Failed to cancel order:', err);
      const detail = err.response?.data?.detail;
      const msg = typeof detail === 'string' ? detail : detail?.message || err.message || 'Unable to cancel order.';
      alert(msg);
    } finally {
      setIsCancellingOrder(false);
    }
  };

  const handleViewOrderDetails = async () => {
    if (!resolvedOrderId) return;

    const requestGeneration = ++detailRequestGeneration.current;
    setLoadingOrder(true);
    try {
      const order = await checkoutService.getOrder(
        resolvedOrderId,
        loadCheckoutCapability(resolvedOrderId),
      );
      if (requestGeneration === detailRequestGeneration.current) {
        setOrderDetails(order);
        setShowOrderModal(true);
      }
    } catch (err) {
      console.error('Error loading order details:', err);
      alert('Unable to load order details');
    } finally {
      if (requestGeneration === detailRequestGeneration.current) {
        setLoadingOrder(false);
      }
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
      <div className="px-4 sm:px-8 py-4 sm:py-6 flex items-center justify-between">
        <div className="flex items-center gap-3 sm:gap-4">
          <Link
            to={ROUTES.HOME}
            className="text-3xl sm:text-4xl text-primary leading-none"
            style={{ fontFamily: 'Lao MN, var(--font-display, serif)' }}
            aria-label="Shopsoma home"
          >
            S
          </Link>
          <button
            onClick={() => navigate(-1)}
            className="text-xs sm:text-sm text-gray-600 hover:text-primary transition flex items-center gap-1 py-1"
          >
            <span>←</span>
            <span>Back</span>
          </button>
        </div>
        <div className="flex items-center gap-3 sm:gap-4">
          <Link
            to={ROUTES.ORDERS}
            className="text-xs sm:text-sm text-primary hover:underline font-medium"
          >
            My Orders
          </Link>
          <span className="text-[10px] sm:text-xs uppercase tracking-[0.2em] sm:tracking-[0.3em] text-gray-500 font-medium">
            Track My Order
          </span>
        </div>
      </div>

      <div className="flex-1 px-3 sm:px-8 pb-12 sm:pb-16">
        <div className="max-w-5xl mx-auto space-y-4 sm:space-y-8">
          {error && (
            <div className="rounded-sm bg-amber-50 border border-amber-200 text-amber-700 text-sm px-4 py-2">
              {error}
            </div>
          )}

          <div className="rounded-sm border border-gray-100 bg-gray-50 px-4 sm:px-6 py-3.5 sm:py-5">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 sm:gap-4">
              <p className="text-xs sm:text-sm font-semibold text-gray-800 break-words">
                Tracking ID{' '}
                <span className="text-primary font-mono ml-1">
                  {tracking?.tracking_id || 'Loading...'}
                </span>
              </p>
              {isPaymentPending && !isTerminalState ? (
                <div className="flex items-center gap-1.5 text-xs text-amber-800 bg-amber-100/90 border border-amber-300 px-2.5 py-0.5 rounded-full font-medium shrink-0">
                  <span className="h-1.5 w-1.5 rounded-full bg-amber-500"></span>
                  <span>Awaiting Payment</span>
                </div>
              ) : isConnectedToWebSocket && !wsError ? (
                <div className="flex items-center gap-2 text-xs text-emerald-600 shrink-0">
                  <span className="relative flex h-2 w-2">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
                  </span>
                  <span>Live Updates Active</span>
                </div>
              ) : wsError ? (
                <div className="flex items-center gap-2 text-xs text-amber-600 shrink-0">
                  <span className="relative flex h-2 w-2">
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-amber-500"></span>
                  </span>
                  <span>Polling for Updates</span>
                </div>
              ) : null}
            </div>
          </div>

          {/* Payment Pending Alert Banner */}
          {isPaymentPending && !isTerminalState && tracking && (
            <div className="rounded-sm p-4 sm:px-6 sm:py-4 border-2 border-amber-300 bg-amber-50/90 text-amber-900 shadow-sm">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div className="flex items-start sm:items-center gap-3">
                  <span className="text-2xl shrink-0">⚠️</span>
                  <div>
                    <p className="font-semibold text-sm">Payment Pending</p>
                    <p className="text-xs mt-0.5 text-amber-800">
                      Payment for this order has not been completed. Fulfillment and dispatch will begin once payment is confirmed.
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-2 shrink-0 pt-2 sm:pt-0">
                  <button
                    type="button"
                    onClick={handleRetryPayment}
                    disabled={isRetryingPayment}
                    className="px-4 py-2 bg-primary text-white text-xs font-semibold rounded-sm hover:bg-primary-dark transition disabled:opacity-50"
                  >
                    {isRetryingPayment ? 'Opening Payment...' : 'Complete Payment'}
                  </button>
                  <button
                    type="button"
                    onClick={handleCancelOrder}
                    disabled={isCancellingOrder}
                    className="px-3 py-2 border border-amber-300 bg-white text-gray-700 text-xs font-semibold rounded-sm hover:bg-gray-50 transition disabled:opacity-50"
                  >
                    {isCancellingOrder ? 'Cancelling...' : 'Cancel Order'}
                  </button>
                </div>
              </div>
            </div>
          )}

          <div className="bg-white border border-gray-100 rounded-sm p-4 sm:p-8 shadow-sm space-y-6 sm:space-y-8">
            {loading ? (
              <div className="text-center text-sm text-gray-500">Fetching latest tracking updates...</div>
            ) : tracking ? (
              <>
                {/* Terminal State Alert Banner */}
                {isTerminalState && tracking && (
                  <div
                    className={`rounded-sm p-4 sm:px-6 sm:py-4 border-2 ${
                      tracking.current_status === 'cancelled'
                        ? 'bg-gray-50 border-gray-300 text-gray-700'
                        : tracking.current_status === 'returned'
                        ? 'bg-orange-50 border-orange-300 text-orange-700'
                        : 'bg-red-50 border-red-300 text-red-700'
                    }`}
                  >
                    <div className="flex items-start sm:items-center gap-3">
                      <span className="text-2xl shrink-0">
                        {tracking.current_status === 'cancelled' && '❌'}
                        {tracking.current_status === 'returned' && '↩️'}
                        {tracking.current_status === 'delivery_failed' && '⚠️'}
                      </span>
                      <div>
                        <p className="font-semibold text-sm">
                          {TERMINAL_STATES[tracking.current_status]?.label || 'Status Update'}
                        </p>
                        <p className="text-xs mt-1 text-gray-600">
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
                    <div className="overflow-x-auto pb-2 -mx-2 px-2 sm:mx-0 sm:px-0 sm:overflow-visible sm:pb-0">
                      <div className="flex items-center justify-between min-w-[280px]">
                        {STATUS_STEPS.map((step, index) => {
                          const isActive = index <= activeIndex;
                          const isCurrent = index === activeIndex;
                          return (
                            <div key={step.key} className="flex-1 flex flex-col items-center text-center">
                              <div className="flex items-center w-full">
                                {index > 0 && (
                                  <span
                                    className={`flex-1 h-0.5 sm:h-px ${
                                      index <= activeIndex ? 'bg-primary' : 'bg-gray-200'
                                    }`}
                                  />
                                )}
                                <span
                                  className={`w-7 h-7 sm:w-9 sm:h-9 rounded-full border-2 flex items-center justify-center shrink-0 transition-colors ${
                                    isActive
                                      ? 'border-primary bg-primary/10 text-primary'
                                      : 'border-gray-200 text-gray-400'
                                  } ${isCurrent ? 'ring-2 ring-primary/20' : ''}`}
                                >
                                  <span className="text-[11px] sm:text-xs font-semibold">{index + 1}</span>
                                </span>
                                {index < STATUS_STEPS.length - 1 && (
                                  <span
                                    className={`flex-1 h-0.5 sm:h-px ${
                                      index < activeIndex ? 'bg-primary' : 'bg-gray-200'
                                    }`}
                                  />
                                )}
                              </div>
                              <p
                                className={`mt-1.5 sm:mt-2 text-[10px] sm:text-xs leading-tight px-0.5 sm:px-1 max-w-[62px] sm:max-w-none break-words sm:break-normal ${
                                  isCurrent
                                    ? 'text-primary font-semibold'
                                    : isActive
                                    ? 'text-gray-800 font-medium'
                                    : 'text-gray-500'
                                }`}
                              >
                                {step.label}
                              </p>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  </div>
                </div>

                <div className="space-y-1 sm:space-y-2">
                  <p className="text-[10px] sm:text-xs uppercase tracking-[0.2em] text-gray-400 font-medium">
                    Last Updated Date
                  </p>
                  <p className="text-xs sm:text-sm text-gray-700 font-medium">
                    {tracking ? formatDisplayDate(tracking.updated_at) : '—'}
                  </p>
                </div>

                <div className="space-y-3">
                  <p className="text-[10px] sm:text-xs uppercase tracking-[0.2em] text-gray-400 font-medium">
                    Tracking Details
                  </p>
                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-sm">
                      <thead className="hidden sm:table-header-group">
                        <tr className="bg-gray-50 text-gray-500 uppercase text-xs tracking-[0.2em]">
                          <th className="py-3 px-4 font-medium whitespace-nowrap">S/N</th>
                          <th className="py-3 px-4 font-medium whitespace-nowrap">Order ID</th>
                          <th className="py-3 px-4 font-medium whitespace-nowrap">Tracking No.</th>
                          <th className="py-3 px-4 font-medium whitespace-nowrap">Date</th>
                          <th className="py-3 px-4 font-medium whitespace-nowrap">Amount</th>
                          <th className="py-3 px-4 font-medium whitespace-nowrap">Status</th>
                        </tr>
                      </thead>
                      <tbody className="block sm:table-row-group">
                        <tr className="block sm:table-row rounded-lg sm:rounded-none border border-gray-100 sm:border-b sm:border-gray-100 bg-gray-50/50 sm:bg-transparent p-4 sm:p-0 space-y-2.5 sm:space-y-0">
                          <td className="flex items-center justify-between sm:table-cell py-1.5 sm:py-3 px-0 sm:px-4 text-gray-700 border-b border-gray-200/40 sm:border-0">
                            <span className="text-xs uppercase tracking-wider text-gray-400 font-medium sm:hidden">S/N</span>
                            <span className="text-xs sm:text-sm">1.</span>
                          </td>
                          <td className="flex items-center justify-between sm:table-cell py-1.5 sm:py-3 px-0 sm:px-4 border-b border-gray-200/40 sm:border-0">
                            <span className="text-xs uppercase tracking-wider text-gray-400 font-medium sm:hidden">Order ID</span>
                            <button
                              onClick={handleViewOrderDetails}
                              disabled={loadingOrder}
                              className="text-primary hover:underline font-semibold disabled:opacity-50 text-right sm:text-left text-xs sm:text-sm break-all sm:break-normal"
                            >
                              {tracking?.order_number || orderId}
                            </button>
                          </td>
                          <td className="flex items-center justify-between sm:table-cell py-1.5 sm:py-3 px-0 sm:px-4 text-gray-700 border-b border-gray-200/40 sm:border-0">
                            <span className="text-xs uppercase tracking-wider text-gray-400 font-medium sm:hidden">Tracking No.</span>
                            <span className="font-mono text-xs sm:text-sm text-gray-800 break-all">{tracking?.tracking_id || '—'}</span>
                          </td>
                          <td className="flex items-center justify-between sm:table-cell py-1.5 sm:py-3 px-0 sm:px-4 text-gray-700 border-b border-gray-200/40 sm:border-0">
                            <span className="text-xs uppercase tracking-wider text-gray-400 font-medium sm:hidden">Date</span>
                            <span className="text-xs sm:text-sm">
                              {tracking
                                ? formatDisplayDate(tracking.history?.[0]?.occurred_at || tracking.updated_at)
                                : '—'}
                            </span>
                          </td>
                          <td className="flex items-center justify-between sm:table-cell py-1.5 sm:py-3 px-0 sm:px-4 text-gray-700 border-b border-gray-200/40 sm:border-0">
                            <span className="text-xs uppercase tracking-wider text-gray-400 font-medium sm:hidden">Amount</span>
                            <span className="font-semibold sm:font-normal text-xs sm:text-sm text-gray-900">
                              {tracking
                                ? new Intl.NumberFormat('en-NG', {
                                    style: 'currency',
                                    currency: tracking.currency || 'NGN',
                                    maximumFractionDigits: 0,
                                  }).format(tracking.amount || 0)
                                : '—'}
                            </span>
                          </td>
                          <td className="flex items-center justify-between sm:table-cell py-1.5 sm:py-3 px-0 sm:px-4">
                            <span className="text-xs uppercase tracking-wider text-gray-400 font-medium sm:hidden">Status</span>
                            <span
                              className={`inline-flex px-3 py-1 rounded-full text-xs font-semibold ${
                                isTerminalState
                                  ? tracking?.current_status === 'cancelled'
                                    ? 'bg-gray-100 text-gray-700'
                                    : tracking?.current_status === 'returned'
                                    ? 'bg-orange-50 text-orange-700'
                                    : 'bg-red-50 text-red-700'
                                  : isPaymentPending
                                  ? 'bg-amber-100 text-amber-800 border border-amber-300'
                                  : activeIndex >= STATUS_STEPS.length - 1
                                  ? 'bg-emerald-50 text-emerald-700'
                                  : activeIndex > 1
                                  ? 'bg-primary/10 text-primary'
                                  : 'bg-amber-50 text-amber-700'
                              }`}
                            >
                              {tracking
                                ? isTerminalState
                                  ? TERMINAL_STATES[tracking.current_status]?.label || 'Cancelled'
                                  : isPaymentPending
                                  ? 'Payment Pending'
                                  : STATUS_STEPS.find((step) => step.key === tracking.current_status)?.label ||
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
            ) : (
              <div className="text-center text-sm text-gray-600" role="status">
                Tracking information is unavailable for this order. Please try again later.
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Order Details Modal */}
      {showOrderModal && orderDetails && (
        <div className="fixed inset-0 bg-black/30 backdrop-blur-sm flex items-center justify-center p-3 sm:p-4 z-50">
          <div className="bg-white rounded-sm sm:rounded-md max-w-2xl w-full max-h-[90vh] overflow-y-auto shadow-xl">
            <div className="sticky top-0 bg-white border-b border-gray-200 px-4 sm:px-6 py-3.5 sm:py-4 flex items-center justify-between z-10">
              <h2 className="text-base sm:text-lg font-semibold text-dark">Order Details</h2>
              <button
                onClick={() => setShowOrderModal(false)}
                className="text-gray-400 hover:text-gray-600 text-2xl leading-none p-1"
                aria-label="Close modal"
              >
                ×
              </button>
            </div>

            <div className="p-4 sm:p-6 space-y-5 sm:space-y-6">
              {/* Order Info */}
              <div className="space-y-2 bg-gray-50/70 p-3 sm:p-4 rounded-sm border border-gray-100">
                <div className="flex flex-col sm:flex-row sm:justify-between text-xs sm:text-sm gap-0.5 sm:gap-2">
                  <span className="text-gray-500">Order Number:</span>
                  <span className="font-semibold break-all text-dark">{orderDetails.order_number}</span>
                </div>
                <div className="flex flex-col sm:flex-row sm:justify-between text-xs sm:text-sm gap-0.5 sm:gap-2">
                  <span className="text-gray-500">Order Date:</span>
                  <span className="font-semibold text-dark">
                    {new Date(orderDetails.created_at).toLocaleDateString('en-US', {
                      year: 'numeric',
                      month: 'long',
                      day: 'numeric',
                    })}
                  </span>
                </div>
                <div className="flex flex-col sm:flex-row sm:justify-between text-xs sm:text-sm gap-0.5 sm:gap-2">
                  <span className="text-gray-500">Payment Status:</span>
                  <span className={`font-semibold uppercase ${
                    orderDetails.payment_status === 'paid'
                      ? 'text-green-600'
                      : orderDetails.payment_status === 'failed'
                      ? 'text-red-600'
                      : 'text-yellow-600'
                  }`}>
                    {orderDetails.payment_status?.replace(/_/g, ' ')}
                  </span>
                </div>
              </div>

              {/* Order Items */}
              <div>
                <h3 className="text-xs sm:text-sm font-semibold text-gray-700 uppercase tracking-[0.2em] mb-3">
                  Items ({orderDetails.items?.length || 0})
                </h3>
                <div className="space-y-3">
                  {orderDetails.items?.map((item: any, index: number) => (
                    <div key={index} className="flex gap-3 border-b border-gray-100 pb-3 items-start">
                      {/* Product Image */}
                      {item.product_image_url && (
                        <div className="shrink-0">
                          <img
                            src={item.product_image_url}
                            alt={item.product_title}
                            className="w-14 h-14 sm:w-16 sm:h-16 object-cover rounded-sm border border-gray-200"
                          />
                        </div>
                      )}

                      {/* Product Details */}
                      <div className="flex-1 min-w-0">
                        <p className="font-medium text-xs sm:text-sm line-clamp-2">{item.product_title}</p>
                        {item.variant_details && (
                          <p className="text-[11px] sm:text-xs text-gray-500 mt-0.5">
                            {item.variant_details.size && `Size: ${item.variant_details.size}`}
                            {item.variant_details.color && ` • Color: ${item.variant_details.color}`}
                          </p>
                        )}
                        <p className="text-[11px] sm:text-xs text-gray-500 mt-0.5">Qty: {item.quantity}</p>
                      </div>

                      {/* Price */}
                      <div className="text-right shrink-0">
                        <p className="font-semibold text-xs sm:text-sm">{formatOrderPrice(item.subtotal)}</p>
                        <p className="text-[10px] sm:text-xs text-gray-500">{formatOrderPrice(item.unit_price)} each</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Order Summary */}
              <div className="border-t border-gray-200 pt-4 space-y-2">
                <div className="flex justify-between text-xs sm:text-sm">
                  <span className="text-gray-600">Subtotal:</span>
                  <span className="font-medium">{formatOrderPrice(orderDetails.subtotal)}</span>
                </div>
                <div className="flex justify-between text-xs sm:text-sm">
                  <span className="text-gray-600">Shipping:</span>
                  <span className="font-medium">{formatOrderPrice(orderDetails.shipping_cost)}</span>
                </div>
                <div className="flex justify-between text-xs sm:text-sm">
                  <span className="text-gray-600">Tax:</span>
                  <span className="font-medium">{formatOrderPrice(orderDetails.tax_amount)}</span>
                </div>
                {orderDetails.discount_amount > 0 && (
                  <div className="flex justify-between text-xs sm:text-sm text-green-600">
                    <span>Discount:</span>
                    <span>-{formatOrderPrice(orderDetails.discount_amount)}</span>
                  </div>
                )}
                <div className="flex justify-between text-sm sm:text-base font-bold border-t border-gray-200 pt-2 mt-2">
                  <span>Total:</span>
                  <span>{formatOrderPrice(orderDetails.total_amount)}</span>
                </div>
              </div>

              {/* Close Button */}
              <button
                onClick={() => setShowOrderModal(false)}
                className="w-full rounded-sm bg-gray-100 text-gray-700 font-semibold py-2.5 sm:py-3 text-xs sm:text-sm hover:bg-gray-200 transition"
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
