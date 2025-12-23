/**
 * Admin Order Detail Page
 * Complete order management and details for admins
 */
import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import AdminSidebar from '../../components/admin/AdminSidebar';
import { useToast } from '../../hooks/useToast';
import CurrencySwitcher from '../../components/common/CurrencySwitcher';
import { useCurrencyStore } from '../../store/currencyStore';
import {
  getOrderDetail,
  updateOrderStatus,
  updateShippingInfo,
  cancelOrder,
  processRefund,
} from '../../services/adminOrderService';
import type {
  OrderDetail,
  FulfillmentStatus,
} from '../../services/adminOrderService';
import { getStatusBadgeConfig } from '../../utils/orderStatusMessages';
import { formatPriceWithConversion } from '../../utils/pricing';

export default function AdminOrderDetail() {
  const { orderId } = useParams<{ orderId: string }>();
  const navigate = useNavigate();
  const { toasts, hideToast, success, error, warning } = useToast();
  const { currentCurrency, setCurrency, exchangeRates, fetchExchangeRate } = useCurrencyStore();

  const [order, setOrder] = useState<OrderDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [updating, setUpdating] = useState(false);

  // Edit states
  const [editingStatus, setEditingStatus] = useState(false);
  const [editingShipping, setEditingShipping] = useState(false);
  const [newStatus, setNewStatus] = useState<FulfillmentStatus | ''>('');
  const [statusNotes, setStatusNotes] = useState('');
  const [shippingData, setShippingData] = useState({
    delivery_provider: '',
    tracking_number: '',
    estimated_delivery_date: '',
  });

  // Cancel/Refund modals
  const [showCancelModal, setShowCancelModal] = useState(false);
  const [showRefundModal, setShowRefundModal] = useState(false);
  const [cancelReason, setCancelReason] = useState('');
  const [refundReason, setRefundReason] = useState('');
  const [refundType, setRefundType] = useState<'full' | 'partial'>('full');
  const [refundAmount, setRefundAmount] = useState('');

  // Pickup scheduling modal
  const [showPickupScheduleModal, setShowPickupScheduleModal] = useState(false);
  const [pickupWindowData, setPickupWindowData] = useState({
    pickup_window_start: '',
    pickup_window_end: '',
    courier_name: '',
    rider_id: '',
  });

  const formatDisplayPrice = (amount: number) => {
    return formatPriceWithConversion(amount, 'NGN', currentCurrency, exchangeRates);
  };

  // Load order details
  const loadOrder = useCallback(async () => {
    if (!orderId) return;

    try {
      setLoading(true);
      const data = await getOrderDetail(orderId);
      setOrder(data);
      setNewStatus(data.fulfillment_status);
      setShippingData({
        delivery_provider: data.delivery_provider || '',
        tracking_number: data.tracking_number || '',
        estimated_delivery_date: data.estimated_delivery_date || '',
      });
    } catch (err) {
      console.error('Failed to load order:', err);
      error('Failed to load order details');
    } finally {
      setLoading(false);
    }
  }, [orderId, error]);

  useEffect(() => {
    fetchExchangeRate();
  }, [fetchExchangeRate]);

  useEffect(() => {
    loadOrder();
  }, [loadOrder]);

  // Update order status
  const handleUpdateStatus = async () => {
    if (!order || !newStatus || newStatus === order.fulfillment_status) return;

    // If changing to PICKUP_SCHEDULED, show modal first
    if (newStatus === 'pickup_scheduled') {
      setShowPickupScheduleModal(true);
      setEditingStatus(false);
      return;
    }

    try {
      setUpdating(true);
      await updateOrderStatus(order.id, {
        fulfillment_status: newStatus as FulfillmentStatus,
        admin_notes: statusNotes || undefined,
      });
      success('Order status updated successfully');
      setEditingStatus(false);
      setStatusNotes('');
    } catch (err) {
      console.error('Failed to update status:', err);
      error('Failed to update order status');
      return;
    } finally {
      setUpdating(false);
    }
    try {
      await loadOrder();
    } catch (err) {
      console.error('Failed to refresh order:', err);
      warning('Updated status, but failed to refresh order');
    }
  };

  // Update shipping info
  const handleUpdateShipping = async () => {
    if (!order) return;

    try {
      setUpdating(true);
      await updateShippingInfo(order.id, shippingData);
      success('Shipping information updated successfully');
      setEditingShipping(false);
    } catch (err) {
      console.error('Failed to update shipping:', err);
      error('Failed to update shipping information');
      return;
    } finally {
      setUpdating(false);
    }
    try {
      await loadOrder();
    } catch (err) {
      console.error('Failed to refresh order:', err);
      warning('Updated shipping, but failed to refresh order');
    }
  };

  // Schedule pickup with window
  const handleSchedulePickup = async () => {
    if (!order || !pickupWindowData.pickup_window_start || !pickupWindowData.pickup_window_end) {
      error('Please select both start and end times for pickup window');
      return;
    }

    try {
      setUpdating(true);

      // First update the order status to PICKUP_SCHEDULED with pickup window data
      await updateOrderStatus(order.id, {
        fulfillment_status: 'pickup_scheduled',
        admin_notes: `Pickup scheduled: ${new Date(pickupWindowData.pickup_window_start).toLocaleString()} - ${new Date(pickupWindowData.pickup_window_end).toLocaleTimeString()}${statusNotes ? ` | ${statusNotes}` : ''}`,
        pickup_window_start: pickupWindowData.pickup_window_start,
        pickup_window_end: pickupWindowData.pickup_window_end,
        courier_name: pickupWindowData.courier_name || undefined,
        rider_id: pickupWindowData.rider_id || undefined,
      });

      success('Pickup scheduled successfully');
      setShowPickupScheduleModal(false);
      setPickupWindowData({ pickup_window_start: '', pickup_window_end: '', courier_name: '', rider_id: '' });
      setStatusNotes('');
    } catch (err) {
      console.error('Failed to schedule pickup:', err);
      error('Failed to schedule pickup');
      return;
    } finally {
      setUpdating(false);
    }
    try {
      await loadOrder();
    } catch (err) {
      console.error('Failed to refresh order:', err);
      warning('Pickup scheduled, but failed to refresh order');
    }
  };

  // Cancel order
  const handleCancelOrder = async () => {
    if (!order || !cancelReason.trim()) {
      error('Please provide a cancellation reason');
      return;
    }

    try {
      setUpdating(true);
      await cancelOrder(order.id, {
        cancellation_reason: cancelReason,
        refund: true,
      });
      success('Order cancelled successfully');
      setShowCancelModal(false);
      setCancelReason('');
    } catch (err) {
      console.error('Failed to cancel order:', err);
      error('Failed to cancel order');
      return;
    } finally {
      setUpdating(false);
    }
    try {
      await loadOrder();
    } catch (err) {
      console.error('Failed to refresh order:', err);
      warning('Cancelled order, but failed to refresh order');
    }
  };

  // Process refund
  const handleProcessRefund = async () => {
    if (!order || !refundReason.trim()) {
      error('Please provide a refund reason');
      return;
    }

    if (refundType === 'partial' && (!refundAmount || parseFloat(refundAmount) <= 0)) {
      error('Please enter a valid refund amount');
      return;
    }

    try {
      setUpdating(true);
      await processRefund(order.id, {
        reason: refundReason,
        refund_type: refundType,
        refund_amount: refundType === 'partial' ? parseFloat(refundAmount) : undefined,
      });
      success('Refund processed successfully');
      setShowRefundModal(false);
      setRefundReason('');
      setRefundAmount('');
      await loadOrder();
    } catch (err) {
      console.error('Failed to process refund:', err);
      error('Failed to process refund');
    } finally {
      setUpdating(false);
    }
  };


  if (loading) {
    return (
      <div className="min-h-screen bg-[var(--color-page-bg)] flex">
        <AdminSidebar activeSection="orders" />
        <main className="flex-1 p-8 space-y-6">
          <div className="animate-pulse">
            <div className="h-8 bg-gray-200 rounded w-1/4 mb-4"></div>
            <div className="h-64 bg-gray-200 rounded"></div>
          </div>
        </main>
      </div>
    );
  }

  if (!order) {
    return (
      <div className="min-h-screen bg-[var(--color-page-bg)] flex">
        <AdminSidebar activeSection="orders" />
        <main className="flex-1 p-8 space-y-6">
          <div className="text-center py-12">
            <h2 className="text-2xl font-bold text-gray-900">Order not found</h2>
            <button
              onClick={() => navigate('/admin/orders')}
              className="mt-4 text-[#105E53] hover:text-[#0d4a41]"
            >
              ← Back to orders
            </button>
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[var(--color-page-bg)] flex">
      <AdminSidebar activeSection="orders" />

      <main className="flex-1 p-8 space-y-6">
        {/* Toast Notifications */}
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className={`fixed top-4 right-4 z-50 px-6 py-3 rounded-lg shadow-lg ${
              toast.type === 'success' ? 'bg-green-500' : 'bg-red-500'
            } text-white`}
          >
            <div className="flex items-center gap-2">
              <span>{toast.message}</span>
              <button onClick={() => hideToast(toast.id)} className="text-white hover:text-gray-200">
                ×
              </button>
            </div>
          </div>
        ))}

        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <button
              onClick={() => navigate('/admin/orders')}
              className="text-gray-600 hover:text-gray-900 mb-2 flex items-center gap-1"
            >
              ← Back to orders
            </button>
            <h1 className="text-3xl font-bold text-gray-900">Order #{order.order_number}</h1>
            <p className="mt-1 text-sm text-gray-500">
              Placed {new Date(order.created_at).toLocaleString()}
            </p>
          </div>
          <div className="flex gap-3 items-center">
            <CurrencySwitcher value={currentCurrency} onChange={setCurrency} />
            {order.fulfillment_status !== 'cancelled' && (
              <>
                <button
                  onClick={() => setShowCancelModal(true)}
                  disabled={updating}
                  className="px-4 py-2 border border-red-300 text-red-700 rounded-lg hover:bg-red-50 disabled:opacity-50"
                >
                  Cancel Order
                </button>
                {order.payment_status === 'paid' && (
                  <button
                    onClick={() => setShowRefundModal(true)}
                    disabled={updating}
                    className="px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 disabled:opacity-50"
                  >
                    Process Refund
                  </button>
                )}
              </>
            )}
          </div>
        </div>

        {/* Main Content */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left Column - Order Details */}
          <div className="lg:col-span-2 space-y-6">
            {/* Order Summary */}
            <div className="bg-white rounded-lg shadow p-6">
              <h2 className="text-lg font-semibold text-gray-900 mb-4">Order Summary</h2>
              <div className="space-y-3">
                <div className="flex justify-between">
                  <span className="text-gray-600">Subtotal:</span>
                  <span className="font-medium">{formatDisplayPrice(order.subtotal)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600">Shipping:</span>
                  <span className="font-medium">{formatDisplayPrice(order.shipping_cost)}</span>
                </div>
                {order.tax_amount > 0 && (
                  <div className="flex justify-between">
                    <span className="text-gray-600">Tax:</span>
                    <span className="font-medium">{formatDisplayPrice(order.tax_amount)}</span>
                  </div>
                )}
                {order.discount_amount > 0 && (
                  <div className="flex justify-between text-green-600">
                    <span>Discount:</span>
                    <span className="font-medium">-{formatDisplayPrice(order.discount_amount)}</span>
                  </div>
                )}
                <div className="border-t pt-3 flex justify-between">
                  <span className="text-lg font-semibold">Total:</span>
                  <span className="text-lg font-bold text-[#105E53]">
                    {formatDisplayPrice(order.total_amount)}
                  </span>
                </div>
              </div>
            </div>

            {/* Order Items */}
            <div className="bg-white rounded-lg shadow p-6">
              <h2 className="text-lg font-semibold text-gray-900 mb-4">Order Items</h2>
              <div className="space-y-4">
                {order.items.map((item) => (
                  <div key={item.id} className="flex gap-4 pb-4 border-b last:border-b-0">
                    {/* Product Image */}
                    <div className="flex-shrink-0">
                      {item.product_image_url ? (
                        <img
                          src={item.product_image_url}
                          alt={item.product_title}
                          className="w-20 h-20 object-cover rounded-lg border border-gray-200"
                          onError={(e) => {
                            // Fallback to placeholder on error
                            e.currentTarget.src = 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="80" height="80" viewBox="0 0 80 80"%3E%3Crect fill="%23f3f4f6" width="80" height="80"/%3E%3Ctext x="50%25" y="50%25" dominant-baseline="middle" text-anchor="middle" font-family="sans-serif" font-size="14" fill="%239ca3af"%3ENo Image%3C/text%3E%3C/svg%3E';
                          }}
                        />
                      ) : (
                        <div className="w-20 h-20 bg-gray-100 rounded-lg flex items-center justify-center">
                          <svg className="w-8 h-8 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                          </svg>
                        </div>
                      )}
                    </div>

                    {/* Product Details */}
                    <div className="flex-1">
                      <h3 className="font-medium text-gray-900">{item.product_title}</h3>
                      {formatVariantDetails(item.variant_details) && (
                        <p className="text-sm text-gray-500">
                          {formatVariantDetails(item.variant_details)}
                        </p>
                      )}
                      <p className="text-sm text-gray-600 mt-1">
                        Vendor: {item.vendor.business_name}
                      </p>
                    </div>

                    {/* Pricing */}
                    <div className="text-right">
                      <div className="font-medium">{formatDisplayPrice(item.unit_price)}</div>
                      <div className="text-sm text-gray-500">Qty: {item.quantity}</div>
                      <div className="text-sm font-medium mt-1">{formatDisplayPrice(item.subtotal)}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Shipping Information */}
            <div className="bg-white rounded-lg shadow p-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-semibold text-gray-900">Shipping Information</h2>
                {!editingShipping && (
                  <button
                    onClick={() => setEditingShipping(true)}
                    className="text-[#105E53] hover:text-[#0d4a41] text-sm"
                  >
                    Edit
                  </button>
                )}
              </div>

              {editingShipping ? (
                <div className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Delivery Provider
                    </label>
                    <input
                      type="text"
                      value={shippingData.delivery_provider}
                      onChange={(e) => setShippingData({ ...shippingData, delivery_provider: e.target.value })}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg"
                      placeholder="e.g., DHL, FedEx"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Tracking Number
                    </label>
                    <input
                      type="text"
                      value={shippingData.tracking_number}
                      onChange={(e) => setShippingData({ ...shippingData, tracking_number: e.target.value })}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg"
                      placeholder="Enter tracking number"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Estimated Delivery
                    </label>
                    <input
                      type="date"
                      value={shippingData.estimated_delivery_date}
                      onChange={(e) => setShippingData({ ...shippingData, estimated_delivery_date: e.target.value })}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg"
                    />
                  </div>
                  <div className="flex gap-3">
                    <button
                      onClick={handleUpdateShipping}
                      disabled={updating}
                      className="px-4 py-2 bg-[#105E53] text-white rounded-lg hover:bg-[#0d4a41] disabled:opacity-50"
                    >
                      {updating ? 'Saving...' : 'Save'}
                    </button>
                    <button
                      onClick={() => setEditingShipping(false)}
                      disabled={updating}
                      className="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <div className="space-y-2">
                  <div>
                    <span className="text-sm text-gray-600">Provider:</span>{' '}
                    <span className="font-medium">{order.delivery_provider || 'Not set'}</span>
                  </div>
                  <div>
                    <span className="text-sm text-gray-600">Tracking:</span>{' '}
                    <span className="font-medium">{order.tracking_number || 'Not set'}</span>
                  </div>
                  <div>
                    <span className="text-sm text-gray-600">Est. Delivery:</span>{' '}
                    <span className="font-medium">
                      {order.estimated_delivery_date
                        ? new Date(order.estimated_delivery_date).toLocaleDateString()
                        : 'Not set'}
                    </span>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Right Column - Status & Customer Info */}
          <div className="space-y-6">
            {/* Order Status */}
            <div className="bg-white rounded-lg shadow p-6">
              <h2 className="text-lg font-semibold text-gray-900 mb-4">Order Status</h2>

              {editingStatus ? (
                <div className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Status
                    </label>
                    <select
                      value={newStatus}
                      onChange={(e) => setNewStatus(e.target.value as FulfillmentStatus)}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg"
                    >
                      <option value="order_received">Order Received</option>
                      <option value="preparing_for_pickup">Preparing for Pickup</option>
                      <option value="pickup_scheduled">Pickup Scheduled</option>
                      <option value="picked_up">Picked Up</option>
                      <option value="in_transit">In Transit</option>
                      <option value="out_for_delivery">Out for Delivery</option>
                      <option value="delivered">Delivered</option>
                      <option value="delivery_failed">Delivery Failed</option>
                      <option value="returned">Returned</option>
                      <option value="cancelled">Cancelled</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Notes (optional)
                    </label>
                    <textarea
                      value={statusNotes}
                      onChange={(e) => setStatusNotes(e.target.value)}
                      rows={3}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg"
                      placeholder="Add notes about this status change..."
                    />
                  </div>
                  <div className="flex gap-3">
                    <button
                      onClick={handleUpdateStatus}
                      disabled={updating || newStatus === order.fulfillment_status}
                      className="flex-1 px-4 py-2 bg-[#105E53] text-white rounded-lg hover:bg-[#0d4a41] disabled:opacity-50"
                    >
                      {updating ? 'Updating...' : 'Update'}
                    </button>
                    <button
                      onClick={() => {
                        setEditingStatus(false);
                        setNewStatus(order.fulfillment_status);
                        setStatusNotes('');
                      }}
                      disabled={updating}
                      className="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <div>
                  <div className="flex items-center justify-between mb-4">
                    {(() => {
                      const badgeConfig = getStatusBadgeConfig(order.fulfillment_status, 'admin');
                      return (
                        <span className={`px-3 py-1 rounded-full text-sm font-medium ${badgeConfig.bgColor} ${badgeConfig.textColor}`}>
                          {badgeConfig.label}
                        </span>
                      );
                    })()}
                    <button
                      onClick={() => setEditingStatus(true)}
                      className="text-[#105E53] hover:text-[#0d4a41] text-sm"
                    >
                      Update
                    </button>
                  </div>
                  <div className="space-y-2 text-sm">
                    <div>
                      <span className="text-gray-600">Payment:</span>{' '}
                      <span className="font-medium capitalize">{order.payment_status}</span>
                    </div>
                    {order.delivered_at && (
                      <div>
                        <span className="text-gray-600">Delivered:</span>{' '}
                        <span className="font-medium">{new Date(order.delivered_at).toLocaleDateString()}</span>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>

            {/* Customer Information */}
            <div className="bg-white rounded-lg shadow p-6">
              <h2 className="text-lg font-semibold text-gray-900 mb-4">Customer</h2>
              <div className="space-y-2 text-sm">
                <div className="font-medium">
                  {order.customer.first_name} {order.customer.last_name}
                </div>
                <div className="text-gray-600">{order.customer.email}</div>
                {order.customer.phone && (
                  <div className="text-gray-600">{order.customer.phone}</div>
                )}
              </div>
            </div>

            {/* Shipping Address */}
            {order.shipping_address && (
              <div className="bg-white rounded-lg shadow p-6">
                <h2 className="text-lg font-semibold text-gray-900 mb-4">Shipping Address</h2>
                <div className="text-sm space-y-1">
                  <div className="font-medium">{order.shipping_address.full_name}</div>
                  <div>{order.shipping_address.street_address}</div>
                  <div>
                    {order.shipping_address.city}, {order.shipping_address.state} {order.shipping_address.postal_code}
                  </div>
                  <div>{order.shipping_address.country}</div>
                  <div className="text-gray-600 mt-2">{order.shipping_address.phone}</div>
                </div>
              </div>
            )}
          </div>
        </div>


        {/* Pickup Scheduling Modal */}
        {showPickupScheduleModal && (
          <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
            <div className="bg-white rounded-lg p-6 max-w-md w-full">
              <h3 className="text-lg font-semibold text-gray-900 mb-4">Schedule Pickup</h3>

              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Pickup Window Start *
                  </label>
                  <input
                    type="datetime-local"
                    value={pickupWindowData.pickup_window_start}
                    onChange={(e) => setPickupWindowData({ ...pickupWindowData, pickup_window_start: e.target.value })}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg"
                    required
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Pickup Window End *
                  </label>
                  <input
                    type="datetime-local"
                    value={pickupWindowData.pickup_window_end}
                    onChange={(e) => setPickupWindowData({ ...pickupWindowData, pickup_window_end: e.target.value })}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg"
                    required
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Courier Name (Optional)
                  </label>
                  <input
                    type="text"
                    value={pickupWindowData.courier_name}
                    onChange={(e) => setPickupWindowData({ ...pickupWindowData, courier_name: e.target.value })}
                    placeholder="e.g., DHL Express"
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Rider ID (Optional)
                  </label>
                  <input
                    type="text"
                    value={pickupWindowData.rider_id}
                    onChange={(e) => setPickupWindowData({ ...pickupWindowData, rider_id: e.target.value })}
                    placeholder="e.g., RD-12345"
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Notes (Optional)
                  </label>
                  <textarea
                    value={statusNotes}
                    onChange={(e) => setStatusNotes(e.target.value)}
                    rows={3}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg"
                    placeholder="Additional notes about the pickup..."
                  />
                </div>
              </div>

              <div className="flex gap-3 mt-6">
                <button
                  onClick={handleSchedulePickup}
                  disabled={updating}
                  className="flex-1 px-4 py-2 bg-[#105E53] text-white rounded-lg hover:bg-[#0d4a41] disabled:opacity-50"
                >
                  {updating ? 'Scheduling...' : 'Schedule Pickup'}
                </button>
                <button
                  onClick={() => {
                    setShowPickupScheduleModal(false);
                    setNewStatus(order?.fulfillment_status || '');
                    setPickupWindowData({ pickup_window_start: '', pickup_window_end: '', courier_name: '', rider_id: '' });
                  }}
                  disabled={updating}
                  className="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50"
                >
                  Cancel
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Cancel Order Modal */}
        {showCancelModal && (
          <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
            <div className="bg-white rounded-lg p-6 max-w-md w-full">
              <h3 className="text-lg font-semibold text-gray-900 mb-4">Cancel Order</h3>
              <p className="text-sm text-gray-600 mb-4">
                Please provide a reason for cancelling this order. A refund will be processed automatically.
              </p>
              <textarea
                value={cancelReason}
                onChange={(e) => setCancelReason(e.target.value)}
                rows={4}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg mb-4"
                placeholder="Enter cancellation reason..."
              />
              <div className="flex gap-3">
                <button
                  onClick={handleCancelOrder}
                  disabled={updating || !cancelReason.trim()}
                  className="flex-1 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50"
                >
                  {updating ? 'Cancelling...' : 'Cancel Order'}
                </button>
                <button
                  onClick={() => setShowCancelModal(false)}
                  disabled={updating}
                  className="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50"
                >
                  Close
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Refund Modal */}
        {showRefundModal && (
          <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
            <div className="bg-white rounded-lg p-6 max-w-md w-full">
              <h3 className="text-lg font-semibold text-gray-900 mb-4">Process Refund</h3>

              <div className="mb-4">
                <label className="block text-sm font-medium text-gray-700 mb-2">Refund Type</label>
                <div className="flex gap-4">
                  <label className="flex items-center">
                    <input
                      type="radio"
                      value="full"
                      checked={refundType === 'full'}
                      onChange={(e) => setRefundType(e.target.value as 'full' | 'partial')}
                      className="mr-2"
                    />
                    Full ({formatDisplayPrice(order.total_amount)})
                  </label>
                  <label className="flex items-center">
                    <input
                      type="radio"
                      value="partial"
                      checked={refundType === 'partial'}
                      onChange={(e) => setRefundType(e.target.value as 'full' | 'partial')}
                      className="mr-2"
                    />
                    Partial
                  </label>
                </div>
              </div>

              {refundType === 'partial' && (
                <div className="mb-4">
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Refund Amount
                  </label>
                  <input
                    type="number"
                    value={refundAmount}
                    onChange={(e) => setRefundAmount(e.target.value)}
                    step="0.01"
                    max={order.total_amount}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg"
                    placeholder="Enter amount"
                  />
                </div>
              )}

              <div className="mb-4">
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Reason
                </label>
                <textarea
                  value={refundReason}
                  onChange={(e) => setRefundReason(e.target.value)}
                  rows={3}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg"
                  placeholder="Enter refund reason..."
                />
              </div>

              <div className="flex gap-3">
                <button
                  onClick={handleProcessRefund}
                  disabled={updating || !refundReason.trim()}
                  className="flex-1 px-4 py-2 bg-[#105E53] text-white rounded-lg hover:bg-[#0d4a41] disabled:opacity-50"
                >
                  {updating ? 'Processing...' : 'Process Refund'}
                </button>
                <button
                  onClick={() => setShowRefundModal(false)}
                  disabled={updating}
                  className="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50"
                >
                  Close
                </button>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
  const formatVariantDetails = (variantDetails?: Record<string, any>) => {
    if (!variantDetails) return null;
    const parts: string[] = [];
    if (variantDetails.size) parts.push(`Size: ${variantDetails.size}`);
    if (variantDetails.color) parts.push(`Color: ${variantDetails.color}`);
    if (parts.length === 0) return null;
    return parts.join(' • ');
  };
