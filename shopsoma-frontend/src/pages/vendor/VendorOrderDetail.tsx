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
} from 'lucide-react';
import VendorSidebar from '../../components/vendor/VendorSidebar';
import { ROUTES } from '../../config/constants';
import { getVendorOrder, type VendorOrder, type VendorOrderItem, type VendorPickup, type PickupStatus } from '../../services/orderService';
import { useToast } from '../../hooks/useToast';
import ToastContainer from '../../components/ui/ToastContainer';

function formatCurrency(amount: number, currency = 'USD') {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency }).format(amount);
}

function StatusPill({ label, tone = 'neutral' }: { label: string; tone?: 'success' | 'warning' | 'neutral' }) {
  const base = 'px-3 py-1 rounded-full text-xs font-semibold inline-flex items-center gap-2';
  if (tone === 'success') return <span className={`${base} bg-emerald-50 text-emerald-700`}>{label}</span>;
  if (tone === 'warning') return <span className={`${base} bg-amber-50 text-amber-700`}>{label}</span>;
  return <span className={`${base} bg-gray-100 text-gray-700`}>{label}</span>;
}

// Shipping Status Card Component
function ShippingStatusCard({ pickup }: { pickup: VendorPickup | null }) {
  if (!pickup) {
    return (
      <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6">
        <div className="flex items-center gap-3 mb-4">
          <div className="h-11 w-11 rounded-xl bg-gray-100 flex items-center justify-center">
            <Truck className="w-5 h-5 text-gray-400" />
          </div>
          <div>
            <p className="text-sm font-semibold text-gray-900">Shipping Status</p>
            <p className="text-xs text-gray-500">No pickup scheduled yet</p>
          </div>
        </div>
        <div className="text-sm text-gray-600">
          <p>Shopsoma will schedule a pickup once your order preparation is confirmed.</p>
        </div>
      </div>
    );
  }

  // Map pickup status to progress percentage and display
  const getPickupProgress = (status: PickupStatus): number => {
    const progressMap: Record<PickupStatus, number> = {
      scheduled: 10,
      in_transit: 30,
      delivered_to_qc: 50,
      qc_approved: 70,
      qc_rejected: 50,
      shipped_to_customer: 85,
      completed: 100,
      cancelled: 0,
    };
    return progressMap[status] || 0;
  };

  const getStatusLabel = (status: PickupStatus): string => {
    const labelMap: Record<PickupStatus, string> = {
      scheduled: 'Pickup Scheduled',
      in_transit: 'In Transit to QC',
      delivered_to_qc: 'Delivered to QC Center',
      qc_approved: 'QC Approved',
      qc_rejected: 'QC Rejected',
      shipped_to_customer: 'Shipped to Customer',
      completed: 'Delivered',
      cancelled: 'Cancelled',
    };
    return labelMap[status] || status;
  };

  const getOriginLabel = (): string => {
    if (pickup.pickup_address) {
      return pickup.pickup_address.substring(0, 30) + (pickup.pickup_address.length > 30 ? '...' : '');
    }
    return 'Vendor Location';
  };

  const getDestinationLabel = (status: PickupStatus): string => {
    if (status === 'completed') return 'Delivered';
    if (status === 'shipped_to_customer') return 'En Route to Customer';
    if (['qc_approved', 'qc_rejected', 'delivered_to_qc'].includes(status)) return 'QC Center';
    if (status === 'in_transit') return 'In Transit';
    return 'Pending Pickup';
  };

  const progress = getPickupProgress(pickup.status);
  const isRejected = pickup.status === 'qc_rejected';
  const isCancelled = pickup.status === 'cancelled';

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
          <p className="text-sm font-semibold text-gray-900">Shipping Status</p>
          <p className="text-xs text-gray-500">{getStatusLabel(pickup.status)}</p>
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
            <span className="text-sm text-gray-700">{getDestinationLabel(pickup.status)}</span>
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
        {pickup.tracking_number && (
          <div>
            <p className="text-xs text-gray-500 mb-1">Tracking Number</p>
            <p className="font-medium text-gray-900">{pickup.tracking_number}</p>
          </div>
        )}
        {pickup.logistics_partner && (
          <div>
            <p className="text-xs text-gray-500 mb-1">Logistics Partner</p>
            <p className="font-medium text-gray-900">{pickup.logistics_partner}</p>
          </div>
        )}
        {pickup.scheduled_pickup_date && (
          <div>
            <p className="text-xs text-gray-500 mb-1">Scheduled Pickup</p>
            <p className="font-medium text-gray-900">
              {new Date(pickup.scheduled_pickup_date).toLocaleDateString()}
            </p>
          </div>
        )}
        {pickup.actual_pickup_date && (
          <div>
            <p className="text-xs text-gray-500 mb-1">Actual Pickup</p>
            <p className="font-medium text-gray-900">
              {new Date(pickup.actual_pickup_date).toLocaleDateString()}
            </p>
          </div>
        )}
        {pickup.qc_center_arrival_date && (
          <div>
            <p className="text-xs text-gray-500 mb-1">QC Center Arrival</p>
            <p className="font-medium text-gray-900">
              {new Date(pickup.qc_center_arrival_date).toLocaleDateString()}
            </p>
          </div>
        )}
        {pickup.qc_approved_date && (
          <div>
            <p className="text-xs text-gray-500 mb-1">QC Approved</p>
            <p className="font-medium text-gray-900">
              {new Date(pickup.qc_approved_date).toLocaleDateString()}
            </p>
          </div>
        )}
      </div>

      {/* QC Notes */}
      {pickup.qc_notes && (
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
      {pickup.vendor_notes && (
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

  const [order, setOrder] = useState<VendorOrder | null>(null);
  const [loading, setLoading] = useState(true);

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
        setOrder(data);
      } catch (err: any) {
        console.error('Failed to load order', err);
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

  if (loading) {
    return (
      <div className="flex min-h-screen bg-gray-50">
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
    <div className="flex min-h-screen bg-gray-50">
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

            <div className="flex items-center gap-3">
              <button
                type="button"
                className="flex items-center gap-2 px-3 py-2 bg-white border border-gray-200 rounded-full shadow-sm text-sm font-semibold text-gray-700"
              >
                <span>$ USD</span>
                <ChevronDown className="w-4 h-4" />
              </button>
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
                  ₦{order.items.reduce((sum, item) => sum + item.vendor_payout, 0).toFixed(2)}
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

            {/* Shipping Status - Compact Card Version */}
            <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-5">
              <div className="flex items-center gap-3 mb-3">
                <div className={`h-11 w-11 rounded-xl flex items-center justify-center flex-shrink-0 ${
                  primaryPickup
                    ? primaryPickup.status === 'cancelled' ? 'bg-gray-100'
                      : primaryPickup.status === 'qc_rejected' ? 'bg-rose-100'
                      : 'bg-[#0B1D2C]'
                    : 'bg-gray-100'
                }`}>
                  <Truck className={`w-5 h-5 ${
                    primaryPickup
                      ? primaryPickup.status === 'cancelled' ? 'text-gray-400'
                        : primaryPickup.status === 'qc_rejected' ? 'text-rose-600'
                        : 'text-white'
                      : 'text-gray-400'
                  }`} />
                </div>
                <div className="min-w-0 overflow-hidden">
                  <p className="text-[11px] uppercase tracking-[0.2em] text-gray-400">Shipping</p>
                  <p className="text-sm font-semibold text-gray-900 mt-1 truncate">
                    {primaryPickup
                      ? primaryPickup.status === 'scheduled' ? 'Pickup Scheduled'
                        : primaryPickup.status === 'in_transit' ? 'In Transit'
                        : primaryPickup.status === 'delivered_to_qc' ? 'At QC Center'
                        : primaryPickup.status === 'qc_approved' ? 'QC Approved'
                        : primaryPickup.status === 'shipped_to_customer' ? 'Shipped'
                        : primaryPickup.status === 'completed' ? 'Delivered'
                        : primaryPickup.status
                      : 'Not Scheduled'
                    }
                  </p>
                </div>
              </div>
              {primaryPickup && (
                <div className="relative h-1.5 bg-gray-100 rounded-full overflow-hidden">
                  <div
                    className={`absolute top-0 left-0 h-full rounded-full transition-all duration-500 ${
                      primaryPickup.status === 'cancelled' ? 'bg-gray-400'
                        : primaryPickup.status === 'qc_rejected' ? 'bg-rose-500'
                        : 'bg-[#105E53]'
                    }`}
                    style={{
                      width: `${
                        primaryPickup.status === 'scheduled' ? 10
                          : primaryPickup.status === 'in_transit' ? 30
                          : primaryPickup.status === 'delivered_to_qc' ? 50
                          : primaryPickup.status === 'qc_approved' ? 70
                          : primaryPickup.status === 'qc_rejected' ? 50
                          : primaryPickup.status === 'shipped_to_customer' ? 85
                          : primaryPickup.status === 'completed' ? 100
                          : 0
                      }%`
                    }}
                  />
                </div>
              )}
            </div>
          </div>

          {/* Detailed Shipping Status Card (Expanded View) */}
          {primaryPickup && (
            <ShippingStatusCard pickup={primaryPickup} />
          )}

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
                {order.items.map((item) => (
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
                      <p className="text-sm text-gray-700 mt-1">₦{item.unit_price.toFixed(2)} · Qty: {item.quantity}</p>
                      <p className="text-xs text-gray-500 mt-1">Payout: ₦{item.vendor_payout.toFixed(2)}</p>
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
                ))}
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

      <ToastContainer toasts={toasts} onDismiss={hideToast} />
    </div>
  );
}
