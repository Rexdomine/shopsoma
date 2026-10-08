import { useEffect, useState } from 'react';
import { Link, useNavigate, useSearchParams, useParams } from 'react-router-dom';
import { ROUTES } from '../../config/constants';
import { checkoutService } from '../../services/checkoutService';
import { paymentService, buildPaystackWidgetConfig } from '../../services/paymentService';
import { useCartStore } from '../../store/cartStore';
import { useCurrencyStore } from '../../store/currencyStore';
import { formatPriceWithConversion, type Currency } from '../../utils/pricing';
import { loadCheckoutCapability } from '../../utils/checkoutCapability';

interface Order {
  id: string;
  order_number: string;
  total_amount: number;
  currency?: Currency;
  payment_status: string;
  fulfillment_status: string;
  created_at: string;
  items: any[];
}

const mockOrder: Order = {
  id: 'demo-order-id',
  order_number: 'SS-102938',
  total_amount: 45200,
  currency: 'NGN',
  payment_status: 'paid',
  fulfillment_status: 'processing',
  created_at: new Date().toISOString(),
  items: [
    {
      product_name: 'Adire Midi Dress',
      quantity: 1,
      unit_price: 32000,
      subtotal: 32000,
      product_image: '/images/demo-image-2.svg',
    },
    {
      product_name: 'Handwoven Tote',
      quantity: 1,
      unit_price: 13200,
      subtotal: 13200,
      product_image: '/images/demo-image-3.svg',
    },
  ],
};

export default function OrderSuccess() {
  const navigate = useNavigate();
  const clearCart = useCartStore((state) => state.clearCart);
  const exchangeRates = useCurrencyStore((state) => state.exchangeRates);
  const { orderId: paramOrderId } = useParams<{ orderId: string }>();
  const [searchParams] = useSearchParams();
  const queryOrderId = searchParams.get('orderId');
  const paymentStatus = searchParams.get('payment');
  const isMock = searchParams.get('mock') === '1';

  const orderId = paramOrderId || queryOrderId;

  const [order, setOrder] = useState<Order | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [isRetrying, setIsRetrying] = useState(false);
  const [isCancelling, setIsCancelling] = useState(false);

  useEffect(() => {
    if (isMock) {
      setOrder(mockOrder);
      setLoading(false);
      return;
    }

    // Clear cart on successful payment
    if (paymentStatus === 'success') {
      clearCart();
    }

    if (orderId) {
      loadOrder();
    } else {
      setError('No order ID provided');
      setLoading(false);
    }
  }, [orderId, paymentStatus]);

  const loadOrder = async () => {
    try {
      const orderData = await checkoutService.getOrder(orderId!, loadCheckoutCapability(orderId));
      setOrder(orderData);
    } catch (err: any) {
      console.error('Error loading order:', err);
      setError('Unable to load order details');
    } finally {
      setLoading(false);
    }
  };

  const handleTrackOrder = () => {
    if (orderId || isMock) {
      navigate(ROUTES.ORDER_TRACKING.replace(':orderId', orderId || mockOrder.id));
    } else {
      navigate(ROUTES.HOME);
    }
  };

  const handleRetryPayment = async () => {
    if (!order) return;
    setIsRetrying(true);
    try {
      const email = (order as any).customer_email || (order as any).customer?.email || 'guest@shopsoma.com';
      const paymentData = await paymentService.initializePayment({
        order_id: order.id,
        email,
        payment_gateway: 'paystack',
        currency: (order.currency as any) || 'NGN',
        callback_url: `${window.location.origin}/payment/verify`,
      }, loadCheckoutCapability(order.id));

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
              clearCart();
              window.location.href = `${ROUTES.ORDER_SUCCESS}?orderId=${order.id}&payment=success`;
            }).catch((err) => {
              console.error('Verification error:', err);
              window.location.href = `${ROUTES.ORDER_SUCCESS}?orderId=${order.id}&payment=verification_failed`;
            });
          },
          onClose: () => {
            setIsRetrying(false);
          },
        });
        handler.openIframe();
      } else if (paymentData.authorization_url) {
        window.location.href = paymentData.authorization_url;
      }
    } catch (err: any) {
      console.error('Failed to initialize payment:', err);
      const detail = err.response?.data?.detail;
      const msg = typeof detail === 'string' ? detail : detail?.message || err.message || 'Unable to start payment.';
      alert(msg);
      setIsRetrying(false);
    }
  };

  const handleCancelOrder = async () => {
    if (!order) return;
    if (!window.confirm('Are you sure you want to cancel this order?')) return;
    setIsCancelling(true);
    try {
      await checkoutService.cancelOrder(order.id, 'Customer cancelled unpaid order', loadCheckoutCapability(order.id));
      setOrder({ ...order, fulfillment_status: 'cancelled' });
      alert('Order has been cancelled.');
    } catch (err: any) {
      console.error('Failed to cancel order:', err);
      const detail = err.response?.data?.detail;
      const msg = typeof detail === 'string' ? detail : detail?.message || err.message || 'Unable to cancel order.';
      alert(msg);
    } finally {
      setIsCancelling(false);
    }
  };

  const getStatusConfig = () => {
    if (order?.fulfillment_status === 'cancelled') {
      return {
        title: 'Order Cancelled',
        subtitle: 'This order has been cancelled',
        icon: '✕',
        iconColor: 'text-gray-500',
        message: 'No charge was made. You can browse and place a new order anytime.',
      };
    } else if (paymentStatus === 'success' || order?.payment_status === 'paid') {
      return {
        title: 'Payment Successful',
        subtitle: 'Your order has been confirmed',
        icon: '✓',
        iconColor: 'text-green-600',
        message: 'Thanks for your purchase. We are preparing your order.',
      };
    } else if (paymentStatus === 'cancelled' || order?.payment_status === 'pending') {
      return {
        title: 'Payment Pending',
        subtitle: 'Order saved, awaiting payment',
        icon: '⚠',
        iconColor: 'text-amber-600',
        message: 'Your items are reserved. Complete payment to process and ship your order, or cancel if you no longer wish to purchase.',
      };
    } else if (paymentStatus === 'verification_failed') {
      return {
        title: 'Payment Verification Failed',
        subtitle: 'We could not verify your payment',
        icon: '!',
        iconColor: 'text-red-600',
        message: 'Please contact support if amount was deducted.',
      };
    }
    return {
      title: 'Order Placed',
      subtitle: 'Your order has been placed',
      icon: 'ℹ',
      iconColor: 'text-blue-600',
      message: 'Complete payment to process your order.',
    };
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-white flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mx-auto mb-4"></div>
          <p className="text-sm text-gray-500">Loading order details...</p>
        </div>
      </div>
    );
  }

  if (error || !order) {
    return (
      <div className="min-h-screen bg-white flex flex-col">
        <div className="px-4 sm:px-8 py-4 sm:py-6">
          <Link
            to={ROUTES.HOME}
            className="text-3xl sm:text-4xl text-primary leading-none"
            style={{ fontFamily: 'Lao MN, var(--font-display, serif)' }}
            aria-label="Shopsoma home"
          >
            S
          </Link>
        </div>
        <div className="flex-1 flex items-center justify-center px-4">
          <div className="text-center">
            <p className="text-4xl mb-4">✕</p>
            <h1 className="text-xl font-semibold text-dark mb-2">Error</h1>
            <p className="text-sm text-gray-500 mb-6">{error || 'Order not found'}</p>
            <Link
              to={ROUTES.HOME}
              className="text-primary font-semibold text-sm hover:underline"
            >
              Return to Home
            </Link>
          </div>
        </div>
      </div>
    );
  }

  const status = getStatusConfig();
  const orderCurrency = (order.currency || 'NGN') as Currency;
  const formattedTotal = formatPriceWithConversion(
    order.total_amount,
    'NGN',
    orderCurrency,
    exchangeRates
  );

  return (
    <div className="min-h-screen bg-white flex flex-col">
      <div className="px-4 sm:px-8 py-4 sm:py-6">
        <Link
          to={ROUTES.HOME}
          className="text-3xl sm:text-4xl text-primary leading-none"
          style={{ fontFamily: 'Lao MN, var(--font-display, serif)' }}
          aria-label="Shopsoma home"
        >
          S
        </Link>
      </div>

      <div className="flex-1 flex flex-col items-center justify-center px-4 py-8 sm:py-12">
        <div className="w-full max-w-2xl space-y-6 sm:space-y-8">
          {/* Status Icon and Message */}
          <div className="text-center space-y-4">
            <div className={`text-5xl sm:text-6xl ${status.iconColor}`}>{status.icon}</div>
            <div className="space-y-2">
              <p className="text-xs sm:text-sm font-semibold text-gray-500 uppercase tracking-[0.3em]">
                {status.subtitle}
              </p>
              <h1 className="text-xl sm:text-2xl font-semibold text-dark">{status.title}</h1>
              <p className="text-xs sm:text-sm text-gray-500">{status.message}</p>
            </div>
          </div>

          {/* Order Details Card */}
          <div className="bg-gray-50 border border-gray-200 rounded-sm p-4 sm:p-6 space-y-4">
            <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-[0.2em]">
              Order Summary
            </h2>

            <div className="space-y-3 text-sm">
              <div className="flex justify-between">
                <span className="text-gray-600">Order Number:</span>
                <span className="font-semibold text-dark">{order.order_number}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-600">Order Date:</span>
                <span className="font-semibold text-dark">
                  {new Date(order.created_at).toLocaleDateString('en-US', {
                    year: 'numeric',
                    month: 'long',
                    day: 'numeric',
                  })}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-600">Total Amount:</span>
                <span className="font-bold text-dark text-lg">
                  {formattedTotal}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-600">Payment Status:</span>
                <span
                  className={`font-semibold uppercase ${
                    order.payment_status === 'paid'
                      ? 'text-green-600'
                      : order.payment_status === 'failed'
                      ? 'text-red-600'
                      : 'text-yellow-600'
                  }`}
                >
                  {order.payment_status?.replace(/_/g, ' ')}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-600">Items:</span>
                <span className="font-semibold text-dark">{order.items?.length || 0} item(s)</span>
              </div>
            </div>
          </div>

          {/* Action Buttons */}
          <div className="space-y-3">
            {order.fulfillment_status === 'cancelled' ? (
              <>
                <Link
                  to={ROUTES.HOME}
                  className="block w-full rounded-sm bg-primary text-white text-center font-semibold py-3 text-sm hover:bg-primary-dark transition"
                >
                  Continue Shopping
                </Link>
                <button
                  type="button"
                  onClick={handleTrackOrder}
                  className="w-full rounded-sm border border-gray-300 text-center text-gray-700 font-semibold py-3 text-sm hover:border-gray-400 transition"
                >
                  View Order Status
                </button>
              </>
            ) : paymentStatus === 'cancelled' || order.payment_status?.toLowerCase() === 'pending' || order.payment_status?.toLowerCase() === 'failed' ? (
              <>
                <button
                  type="button"
                  onClick={handleRetryPayment}
                  disabled={isRetrying}
                  className="w-full rounded-sm bg-primary text-white font-semibold py-3 text-sm hover:bg-primary-dark transition focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-primary disabled:opacity-50"
                >
                  {isRetrying ? 'Opening Payment...' : 'Complete Payment'}
                </button>

                <button
                  type="button"
                  onClick={handleCancelOrder}
                  disabled={isCancelling}
                  className="w-full rounded-sm border border-red-300 text-red-700 bg-red-50/50 hover:bg-red-50 font-semibold py-3 text-sm transition disabled:opacity-50"
                >
                  {isCancelling ? 'Cancelling...' : 'Cancel This Order'}
                </button>

                <button
                  type="button"
                  onClick={handleTrackOrder}
                  className="w-full rounded-sm border border-gray-300 text-center text-gray-700 font-semibold py-3 text-sm hover:border-gray-400 transition"
                >
                  View Order Tracking
                </button>

                <Link
                  to={ROUTES.ORDERS}
                  className="block w-full rounded-sm border border-gray-300 text-center text-gray-700 font-semibold py-3 text-sm hover:border-gray-400 transition"
                >
                  View All Orders
                </Link>
              </>
            ) : (
              <>
                <button
                  type="button"
                  onClick={handleTrackOrder}
                  className="w-full rounded-sm bg-primary text-white font-semibold py-3 text-sm hover:bg-primary-dark transition focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-primary"
                >
                  Track Order
                </button>

                <Link
                  to={ROUTES.ORDERS}
                  className="block w-full rounded-sm border-2 border-primary text-primary hover:bg-primary hover:text-white text-center font-semibold py-3 text-sm transition"
                >
                  View All Orders
                </Link>

                <Link
                  to={ROUTES.HOME}
                  className="block w-full rounded-sm border-2 border-gray-300 text-center text-gray-700 font-semibold py-3 text-sm hover:border-gray-400 transition"
                >
                  Continue Shopping
                </Link>
              </>
            )}
          </div>

          {/* Help Text */}
          <div className="text-center text-xs text-gray-500">
            <p>
              Need help?{' '}
              <Link to="/support" className="text-primary font-semibold hover:underline">
                Contact Support
              </Link>
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
