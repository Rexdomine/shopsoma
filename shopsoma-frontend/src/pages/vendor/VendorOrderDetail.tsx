import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  ArrowLeft,
  MapPin,
  Package,
  CheckCircle2,
  Loader2,
  ChevronDown,
  Truck,
  ClipboardCheck,
  Home,
  X,
} from 'lucide-react';
import VendorSidebar from '../../components/vendor/VendorSidebar';
import { ROUTES } from '../../config/constants';
import { getVendorOrder, type VendorOrder, type VendorPickup } from '../../services/orderService';
import { useToast } from '../../hooks/useToast';
import ToastContainer from '../../components/ui/ToastContainer';
import { useCurrency } from '../../hooks/useCurrency';

function StatusPill({ label, tone = 'neutral' }: { label: string; tone?: 'success' | 'warning' | 'neutral' }) {
  const base = 'px-3 py-1 rounded-full text-xs font-semibold inline-flex items-center gap-2';
  if (tone === 'success') return <span className={`${base} bg-emerald-50 text-emerald-700`}>{label}</span>;
  if (tone === 'warning') return <span className={`${base} bg-amber-50 text-amber-700`}>{label}</span>;
  return <span className={`${base} bg-gray-100 text-gray-700`}>{label}</span>;
}

// Shipping Status Card Component
function ShippingStatusCard({ order, pickup }: { order: VendorOrder; pickup: VendorPickup | null }) {
  // Map order fulfillment status to progress percentage and display
  const getOrderProgress = (status: string): number => {
    const progressMap: Record<string, number> = {
      'order_received': 5,
      'preparing_for_pickup': 15,
      'pickup_scheduled': 25,
      'picked_up': 40,
      'in_transit': 60,
      'out_for_delivery': 80,
      'delivered': 100,
      'delivery_failed': 80,
      'returned': 50,
      'cancelled': 0,
    };
    return progressMap[status] || 0;
  };

  const getStatusLabel = (status: string): string => {
    const labelMap: Record<string, string> = {
      'order_received': 'New Order - Start Preparing',
      'preparing_for_pickup': 'Pack Order - Awaiting Rider',
      'pickup_scheduled': 'Pickup Scheduled',
      'picked_up': 'Items Picked Up Successfully',
      'in_transit': 'Order In Transit to Customer',
      'out_for_delivery': 'Out for Delivery',
      'delivered': 'Delivered Successfully',
      'delivery_failed': 'Delivery Failed - Action Required',
      'returned': 'Order Returned',
      'cancelled': 'Order Cancelled',
    };
    return labelMap[status] || status.replace('_', ' ').toUpperCase();
  };

  const getOriginLabel = (): string => {
    // Display vendor business name with fallback and error handling
    console.log('[VendorOrderDetail] order.vendor_business_name:', order.vendor_business_name);
    console.log('[VendorOrderDetail] Full order object:', order);

    if (!order.vendor_business_name) {
      console.warn('[VendorOrderDetail] vendor_business_name is missing from order data');
      // Fallback to pickup address if vendor name not available
      if (pickup && pickup.pickup_address) {
        console.log('[VendorOrderDetail] Falling back to pickup_address:', pickup.pickup_address);
        return pickup.pickup_address.substring(0, 30) + (pickup.pickup_address.length > 30 ? '...' : '');
      }
      return 'Vendor Location';
    }

    return order.vendor_business_name;
  };

  const getDestinationLabel = (status: string): string => {
    if (status === 'delivered') return 'Delivered';
    if (status === 'out_for_delivery') return 'En Route to Customer';
    if (['in_transit', 'picked_up'].includes(status)) return 'In Transit';
    if (status === 'pickup_scheduled') return 'Awaiting Pickup';
    return 'Processing';
  };

  const progress = getOrderProgress(order.fulfillment_status);
  const isRejected = order.fulfillment_status === 'returned';
  const isCancelled = order.fulfillment_status === 'cancelled';

  return (
    <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6">
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <div className={`h-11 w-11 rounded-xl flex items-center justify-center ${
          isCancelled ? 'bg-gray-100' : isRejected ? 'bg-rose-100' : 'bg-[#0B1D2C]'
        }`}>
          <Truck className={`w-5 h-5 ${isCancelled ? 'text-gray-400' : isRejected ? 'text-rose-600' : 'text-white'}`} />
        </div>
        <div>
          <p className="text-sm font-semibold text-gray-900">Order Status</p>
          <p className="text-xs text-gray-500">{getStatusLabel(order.fulfillment_status)}</p>
        </div>
      </div>

      {/* Progress Visualization */}
      <div className="mb-6">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Home className="w-4 h-4 text-gray-500" />
            <span className="text-sm text-gray-700">{getOriginLabel()}</span>
          </div>
          <div className="flex items-center gap-2">
            <MapPin className="w-4 h-4 text-gray-500" />
            <span className="text-sm text-gray-700">{getDestinationLabel(order.fulfillment_status)}</span>
          </div>
        </div>

        {/* Progress Bar */}
        <div className="relative h-2 bg-gray-100 rounded-full overflow-hidden">
          <div
            className={`absolute top-0 left-0 h-full rounded-full transition-all duration-500 ${
              isCancelled ? 'bg-gray-400' : isRejected ? 'bg-rose-500' : 'bg-[#105E53]'
            }`}
            style={{ width: `${progress}%` }}
          />
        </div>
        <p className="text-xs text-gray-500 mt-2 text-center">{progress}% Complete</p>
      </div>

      {/* Details Grid */}
      <div className="grid grid-cols-2 gap-4 text-sm">
        {/* Pickup Window - Show when scheduled */}
        {(() => {
          console.log('[ShippingStatusCard] Checking pickup window conditions:');
          console.log('[ShippingStatusCard] pickup exists:', !!pickup);
          console.log('[ShippingStatusCard] pickup.pickup_window_start:', pickup?.pickup_window_start);
          console.log('[ShippingStatusCard] pickup.pickup_window_end:', pickup?.pickup_window_end);
          console.log('[ShippingStatusCard] Will show pickup window?', !!(pickup && pickup.pickup_window_start && pickup.pickup_window_end));
          return null;
        })()}
        {pickup && pickup.pickup_window_start && pickup.pickup_window_end && (
          <div className="col-span-2">
            <p className="text-xs text-gray-500 mb-1">Pickup Window</p>
            <p className="font-medium text-gray-900">
              {new Date(pickup.pickup_window_start).toLocaleString('en-US', {
                month: 'short',
                day: 'numeric',
                year: 'numeric',
                hour: 'numeric',
                minute: '2-digit',
                hour12: true
              })}
              {' - '}
              {new Date(pickup.pickup_window_end).toLocaleString('en-US', {
                hour: 'numeric',
                minute: '2-digit',
                hour12: true
              })}
            </p>
          </div>
        )}
        {pickup && pickup.courier_name && (
          <div>
            <p className="text-xs text-gray-500 mb-1">Courier</p>
            <p className="font-medium text-gray-900">{pickup.courier_name}</p>
          </div>
        )}
        {pickup && pickup.rider_id && (
          <div>
            <p className="text-xs text-gray-500 mb-1">Rider ID</p>
            <p className="font-medium text-gray-900">{pickup.rider_id}</p>
          </div>
        )}
        {pickup && pickup.tracking_number && (
          <div>
            <p className="text-xs text-gray-500 mb-1">Tracking Number</p>
            <p className="font-medium text-gray-900">{pickup.tracking_number}</p>
          </div>
        )}
        {pickup && pickup.logistics_partner && (
          <div>
            <p className="text-xs text-gray-500 mb-1">Logistics Partner</p>
            <p className="font-medium text-gray-900">{pickup.logistics_partner}</p>
          </div>
        )}
        {pickup && pickup.qc_center_arrival_date && (
          <div>
            <p className="text-xs text-gray-500 mb-1">QC Center Arrival</p>
            <p className="font-medium text-gray-900">
              {new Date(pickup.qc_center_arrival_date).toLocaleDateString()}
            </p>
          </div>
        )}
        {pickup && pickup.qc_approved_date && (
          <div>
            <p className="text-xs text-gray-500 mb-1">QC Approved</p>
            <p className="font-medium text-gray-900">
              {new Date(pickup.qc_approved_date).toLocaleDateString()}
            </p>
          </div>
        )}
      </div>

      {/* QC Notes */}
      {pickup && pickup.qc_notes && (
        <div className="mt-4 p-3 bg-amber-50 border border-amber-200 rounded-lg">
          <div className="flex items-start gap-2">
            <ClipboardCheck className="w-4 h-4 text-amber-600 mt-0.5 flex-shrink-0" />
            <div>
              <p className="text-xs font-semibold text-amber-900 mb-1">QC Notes</p>
              <p className="text-sm text-amber-800">{pickup.qc_notes}</p>
            </div>
          </div>
        </div>
      )}

      {/* Vendor Notes */}
      {pickup && pickup.vendor_notes && (
        <div className="mt-4 p-3 bg-blue-50 border border-blue-200 rounded-lg">
          <div className="flex items-start gap-2">
            <Package className="w-4 h-4 text-blue-600 mt-0.5 flex-shrink-0" />
            <div>
              <p className="text-xs font-semibold text-blue-900 mb-1">Your Notes</p>
              <p className="text-sm text-blue-800">{pickup.vendor_notes}</p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function VendorOrderDetail() {
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const { toasts, hideToast, error } = useToast();
  const { currentCurrency, setCurrency, formatBasePrice, getCurrencySymbol } = useCurrency();

  const [order, setOrder] = useState<VendorOrder | null>(null);
  const [loading, setLoading] = useState(true);
  const [isShippingModalOpen, setIsShippingModalOpen] = useState(false);
  const [isCurrencyDropdownOpen, setIsCurrencyDropdownOpen] = useState(false);

  useEffect(() => {
    const fetchOrder = async () => {
      if (!id) {
        error('Order ID is required', 'Error');
        navigate(ROUTES.VENDOR_ORDERS);
        return;
      }

      try {
        setLoading(true);
        const data = await getVendorOrder(id);
        console.log('[VendorOrderDetail] Fetched order data:', data);
        console.log('[VendorOrderDetail] vendor_business_name in response:', data.vendor_business_name);

        // Debug pickup window data
        console.log('[VendorOrderDetail] Number of items:', data.items?.length);
        if (data.items && data.items.length > 0) {
          const firstItem = data.items[0];
          console.log('[VendorOrderDetail] First item pickup data:', firstItem.pickup);
          if (firstItem.pickup) {
            console.log('[VendorOrderDetail] pickup_window_start:', firstItem.pickup.pickup_window_start);
            console.log('[VendorOrderDetail] pickup_window_end:', firstItem.pickup.pickup_window_end);
            console.log('[VendorOrderDetail] scheduled_pickup_date:', firstItem.pickup.scheduled_pickup_date);
            console.log('[VendorOrderDetail] actual_pickup_date:', firstItem.pickup.actual_pickup_date);
          } else {
            console.warn('[VendorOrderDetail] ⚠️ First item has no pickup data');
          }
        }

        setOrder(data);
      } catch (err: any) {
        console.error('Failed to load order', err);
        console.error('[VendorOrderDetail] Error details:', err.response?.data);
        error(
          err.response?.data?.detail || 'Failed to load order',
          'Error'
        );
        navigate(ROUTES.VENDOR_ORDERS);
      } finally {
        setLoading(false);
      }
    };

    fetchOrder();
  }, [id, navigate, error]);

  // Handle escape key to close modal and dropdown
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (isShippingModalOpen) setIsShippingModalOpen(false);
        if (isCurrencyDropdownOpen) setIsCurrencyDropdownOpen(false);
      }
    };

    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [isShippingModalOpen, isCurrencyDropdownOpen]);

  // Handle click outside to close currency dropdown
  useEffect(() => {
    if (!isCurrencyDropdownOpen) return;

    const handleClickOutside = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      // Check if click is outside the currency dropdown
      if (!target.closest('.currency-dropdown-container')) {
        setIsCurrencyDropdownOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isCurrencyDropdownOpen]);

  const getVariantSummary = (variantDetails: VendorOrder['items'][number]['variant_details']) => {
    if (!variantDetails) return null;
    const parts: string[] = [];
    if (variantDetails.size) parts.push(`Size: ${variantDetails.size}`);
    if (variantDetails.color) parts.push(`Color: ${variantDetails.color}`);
    return parts.length > 0 ? parts.join(' • ') : null;
  };

  if (loading) {
    return (
      <div className="flex min-h-screen bg-[var(--color-page-bg)]">
        <VendorSidebar activePrimary="orders" />
        <div className="flex-1 flex items-center justify-center">
          <div className="flex items-center gap-3 text-gray-600">
            <Loader2 className="h-6 w-6 animate-spin" />
            <span>Loading order details...</span>
          </div>
        </div>
      </div>
    );
  }

  if (!order) return null;

  // Get the first item's pickup for the shipping status card
  const primaryPickup = order.items[0]?.pickup || null;

  return (
    <div className="flex min-h-screen bg-[var(--color-page-bg)]">
      <VendorSidebar activePrimary="orders" />

      <div className="flex-1">
        <div className="px-8 py-8 space-y-8">
          {/* Header */}
          <div className="flex flex-wrap items-start justify-between gap-6">
            <div className="flex items-start gap-4">
              <button
                type="button"
                onClick={() => navigate(ROUTES.VENDOR_ORDERS)}
                className="h-11 w-11 rounded-full border border-gray-200 bg-white flex items-center justify-center hover:bg-gray-100 transition"
                aria-label="Back to orders"
              >
                <ArrowLeft className="w-4 h-4 text-gray-700" />
              </button>
              <div>
                <p className="text-sm text-gray-500">Order Management</p>
                <h1 className="text-2xl font-semibold text-gray-900 mt-1">Order {order.order_number}</h1>
                <div className="flex flex-wrap items-center gap-4 mt-2 text-sm text-gray-600">
                  <span>Ordered: {new Date(order.created_at).toLocaleDateString()}</span>
                  <span className="flex items-center gap-2">
                    Order Status:
                    <StatusPill label={order.fulfillment_status} tone={order.fulfillment_status === 'delivered' ? 'success' : 'neutral'} />
                  </span>
                </div>
              </div>
            </div>

            <div className="flex items-center gap-3 relative currency-dropdown-container">
              <button
                type="button"
                onClick={() => setIsCurrencyDropdownOpen(!isCurrencyDropdownOpen)}
                className="flex items-center gap-2 px-3 py-2 bg-white border border-gray-200 rounded-full shadow-sm text-sm font-semibold text-gray-700 hover:bg-gray-50 transition-colors"
              >
                <span>{getCurrencySymbol()} {currentCurrency}</span>
                <ChevronDown className={`w-4 h-4 transition-transform ${isCurrencyDropdownOpen ? 'rotate-180' : ''}`} />
              </button>

              {/* Currency Dropdown */}
              {isCurrencyDropdownOpen && (
                <div className="absolute top-full right-0 mt-2 bg-white border border-gray-200 rounded-xl shadow-lg py-1 min-w-[120px] z-50">
                  <button
                    type="button"
                    onClick={() => {
                      setCurrency('NGN');
                      setIsCurrencyDropdownOpen(false);
                    }}
                    className={`w-full px-4 py-2 text-left text-sm hover:bg-gray-50 transition-colors flex items-center gap-2 ${
                      currentCurrency === 'NGN' ? 'bg-gray-100 font-semibold' : ''
                    }`}
                  >
                    <span>₦ NGN</span>
                    {currentCurrency === 'NGN' && <CheckCircle2 className="w-4 h-4 text-[#105E53] ml-auto" />}
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setCurrency('USD');
                      setIsCurrencyDropdownOpen(false);
                    }}
                    className={`w-full px-4 py-2 text-left text-sm hover:bg-gray-50 transition-colors flex items-center gap-2 ${
                      currentCurrency === 'USD' ? 'bg-gray-100 font-semibold' : ''
                    }`}
                  >
                    <span>$ USD</span>
                    {currentCurrency === 'USD' && <CheckCircle2 className="w-4 h-4 text-[#105E53] ml-auto" />}
                  </button>
                </div>
              )}
            </div>
          </div>

          {/* Top overview - 3 column grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {/* Total Payout */}
            <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-5 flex items-center gap-3">
              <div className="h-11 w-11 rounded-xl bg-[#0B1D2C] text-white flex items-center justify-center shadow-md flex-shrink-0">
                <Package className="w-5 h-5" />
              </div>
              <div className="min-w-0 overflow-hidden">
                <p className="text-[11px] uppercase tracking-[0.2em] text-gray-400">Total Payout</p>
                <p className="text-2xl font-semibold text-[#0B1D2C] mt-2 leading-tight truncate">
                  {formatBasePrice(order.items.reduce((sum, item) => sum + item.vendor_payout, 0))}
                </p>
              </div>
            </div>

            {/* Items Count */}
            <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-5 flex items-center gap-3">
              <div className="h-11 w-11 rounded-xl bg-[#0B1D2C] text-white flex items-center justify-center shadow-md flex-shrink-0">
                <Package className="w-5 h-5" />
              </div>
              <div className="min-w-0">
                <p className="text-[11px] uppercase tracking-[0.2em] text-gray-400">Items Count</p>
                <p className="text-2xl font-semibold text-[#0B1D2C] mt-2 leading-tight">
                  {order.items.reduce((sum, item) => sum + item.quantity, 0)} items
                </p>
              </div>
            </div>

            {/* Order Status - Compact Card Version */}
            <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-5">
              <div className="flex items-center gap-3 mb-3">
                <div className={`h-11 w-11 rounded-xl flex items-center justify-center flex-shrink-0 ${
                  order.fulfillment_status === 'cancelled' ? 'bg-gray-100'
                    : order.fulfillment_status === 'returned' ? 'bg-rose-100'
                    : 'bg-[#0B1D2C]'
                }`}>
                  <Truck className={`w-5 h-5 ${
                    order.fulfillment_status === 'cancelled' ? 'text-gray-400'
                      : order.fulfillment_status === 'returned' ? 'text-rose-600'
                      : 'text-white'
                  }`} />
                </div>
                <div className="min-w-0 overflow-hidden">
                  <p className="text-[11px] uppercase tracking-[0.2em] text-gray-400">ORDER STATUS</p>
                  <p className="text-sm font-semibold text-gray-900 mt-1 truncate">
                    {order.fulfillment_status === 'order_received' ? 'New Order - Start Preparing'
                      : order.fulfillment_status === 'preparing_for_pickup' ? 'Pack Order - Awaiting Rider'
                      : order.fulfillment_status === 'pickup_scheduled' ? 'Pickup Scheduled'
                      : order.fulfillment_status === 'picked_up' ? 'Items Picked Up Successfully'
                      : order.fulfillment_status === 'in_transit' ? 'Order In Transit to Customer'
                      : order.fulfillment_status === 'out_for_delivery' ? 'Out for Delivery'
                      : order.fulfillment_status === 'delivered' ? 'Delivered Successfully'
                      : order.fulfillment_status === 'delivery_failed' ? 'Delivery Failed - Action Required'
                      : order.fulfillment_status === 'returned' ? 'Order Returned'
                      : order.fulfillment_status === 'cancelled' ? 'Order Cancelled'
                      : order.fulfillment_status.replace('_', ' ').toUpperCase()
                    }
                  </p>
                </div>
              </div>
              <div className="relative h-1.5 bg-gray-100 rounded-full overflow-hidden mb-3">
                <div
                  className={`absolute top-0 left-0 h-full rounded-full transition-all duration-500 ${
                    order.fulfillment_status === 'cancelled' ? 'bg-gray-400'
                      : order.fulfillment_status === 'returned' ? 'bg-rose-500'
                      : 'bg-[#105E53]'
                  }`}
                  style={{
                    width: `${
                      order.fulfillment_status === 'order_received' ? 5
                        : order.fulfillment_status === 'preparing_for_pickup' ? 15
                        : order.fulfillment_status === 'pickup_scheduled' ? 25
                        : order.fulfillment_status === 'picked_up' ? 40
                        : order.fulfillment_status === 'in_transit' ? 60
                        : order.fulfillment_status === 'out_for_delivery' ? 80
                        : order.fulfillment_status === 'delivered' ? 100
                        : order.fulfillment_status === 'delivery_failed' ? 80
                        : order.fulfillment_status === 'returned' ? 50
                        : order.fulfillment_status === 'cancelled' ? 0
                        : 0
                    }%`
                  }}
                />
              </div>
              <button
                type="button"
                onClick={() => setIsShippingModalOpen(true)}
                className="text-xs text-gray-500 hover:text-gray-700 transition-colors flex items-center gap-1"
              >
                View More
                <ChevronDown className="w-3 h-3" />
              </button>
            </div>
          </div>

          {/* Details grid */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            {/* Customer & Shipping Info */}
            <div className="lg:col-span-5 bg-white rounded-2xl border border-gray-200 shadow-sm p-6 space-y-5">
              <p className="text-sm font-semibold text-gray-900">Customer & Shipping</p>
              <div className="space-y-4">
                <div>
                  <p className="text-xs text-gray-500 mb-1">Customer</p>
                  <p className="text-sm font-medium text-gray-900">{order.customer_name}</p>
                  <p className="text-xs text-gray-500">{order.customer_email}</p>
                </div>
                {order.shipping_address && (
                  <div>
                    <p className="text-xs text-gray-500 mb-1">Shipping Address</p>
                    <p className="text-sm text-gray-700">{order.shipping_address.address_line1}</p>
                    {order.shipping_address.address_line2 && (
                      <p className="text-sm text-gray-700">{order.shipping_address.address_line2}</p>
                    )}
                    <p className="text-sm text-gray-700">
                      {order.shipping_address.city}, {order.shipping_address.state} {order.shipping_address.postal_code}
                    </p>
                    <p className="text-sm text-gray-700">{order.shipping_address.country}</p>
                  </div>
                )}
                <div>
                  <p className="text-xs text-gray-500 mb-1">Payment Status</p>
                  <p className="text-sm font-medium text-gray-900 capitalize">{order.payment_status}</p>
                </div>
              </div>
            </div>

            <div className="lg:col-span-7 bg-white rounded-2xl border border-gray-200 shadow-sm p-6 space-y-4">
              <div className="flex items-center justify-between">
                <p className="text-sm font-semibold text-gray-900">Order Summary</p>
                <span className="text-xs text-gray-500">{order.items.length} items</span>
              </div>

              <div className="divide-y divide-gray-200">
                {order.items.map((item) => {
                  const variantSummary = getVariantSummary(item.variant_details);
                  return (
                    <div key={item.id} className="py-4 flex items-center gap-4">
                    {/* Product Image or Placeholder */}
                    <div className="h-16 w-16 rounded-xl bg-gray-100 border border-gray-200 overflow-hidden flex-shrink-0">
                      {item.product_image_url ? (
                        <img
                          src={item.product_image_url}
                          alt={item.product_title}
                          className="h-full w-full object-cover"
                          onError={(e) => {
                            // Fallback to placeholder on error
                            e.currentTarget.style.display = 'none';
                            const parent = e.currentTarget.parentElement;
                            if (parent) {
                              parent.classList.add('flex', 'items-center', 'justify-center');
                              const icon = document.createElement('div');
                              icon.innerHTML = '<svg class="h-6 w-6 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"></path></svg>';
                              parent.appendChild(icon);
                            }
                          }}
                        />
                      ) : (
                        <div className="h-full w-full flex items-center justify-center">
                          <Package className="h-6 w-6 text-gray-400" />
                        </div>
                      )}
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-semibold text-gray-900 line-clamp-1">{item.product_title}</p>
                      <p className="text-sm text-gray-700 mt-1">{formatBasePrice(item.unit_price)} · Qty: {item.quantity}</p>
                      {variantSummary && (
                        <p className="text-xs text-gray-500 mt-1">{variantSummary}</p>
                      )}
                      <p className="text-xs text-gray-500 mt-1">Payout: {formatBasePrice(item.vendor_payout)}</p>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className={`px-3 py-1 rounded-full text-xs font-semibold ${
                        item.fulfillment_status === 'delivered' ? 'bg-[#E8F7EF] text-[#19984B]' :
                        item.fulfillment_status === 'shipped' ? 'bg-blue-100 text-blue-700' :
                        item.fulfillment_status === 'processing' ? 'bg-amber-100 text-amber-700' :
                        'bg-gray-100 text-gray-700'
                      }`}>
                        {item.fulfillment_status}
                      </span>
                    </div>
                    </div>
                  );
                })}
              </div>

              {/* Info Message */}
              <div className="mt-4 p-4 bg-blue-50 border border-blue-200 rounded-lg">
                <div className="flex items-start gap-3">
                  <Package className="w-5 h-5 text-blue-600 mt-0.5 flex-shrink-0" />
                  <div>
                    <p className="text-sm font-semibold text-blue-900 mb-1">Vendor Responsibility</p>
                    <p className="text-sm text-blue-800">
                      Your role is to prepare orders for Shopsoma pickup. Fulfillment status updates are managed by the Shopsoma logistics team through the admin panel.
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Order Status Details Modal */}
      {isShippingModalOpen && primaryPickup && (
        <div
          className="fixed inset-0 bg-black/40 backdrop-blur-sm flex items-center justify-center z-50 p-4"
          onClick={() => setIsShippingModalOpen(false)}
        >
          <div
            className="bg-white rounded-2xl shadow-2xl max-w-2xl w-full max-h-[90vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div className="sticky top-0 bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between rounded-t-2xl">
              <h2 className="text-lg font-semibold text-gray-900">Order Status Details</h2>
              <button
                type="button"
                onClick={() => setIsShippingModalOpen(false)}
                className="text-gray-400 hover:text-gray-600 transition-colors p-1 rounded-lg hover:bg-gray-100"
                aria-label="Close modal"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Modal Content - Reuse ShippingStatusCard content */}
            <div className="p-6">
              <ShippingStatusCard order={order} pickup={primaryPickup} />
            </div>
          </div>
        </div>
      )}

      <ToastContainer toasts={toasts} onClose={hideToast} />
    </div>
  );
}
