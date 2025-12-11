import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  ArrowLeft,
  MapPin,
  Package,
  CheckCircle2,
  Pencil,
  X,
  Loader2,
  ChevronDown,
} from 'lucide-react';
import VendorSidebar from '../../components/vendor/VendorSidebar';
import { ROUTES } from '../../config/constants';
import { getVendorOrder, updateVendorOrderItem, type VendorOrder, type VendorOrderItem } from '../../services/orderService';
import { useToast } from '../../hooks/useToast';
import ToastContainer from '../../components/ui/ToastContainer';

type TimelineEntry = {
  date: string;
  time: string;
  title: string;
  description: string;
  state?: 'active' | 'muted';
};

type OrderItem = {
  name: string;
  variant: string;
  price: number;
  quantity: number;
  status: 'low' | 'ok' | 'delayed';
  image: string;
  stock?: number;
  size?: string;
  color?: string;
};

const mockDetail = {
  id: 'BZV6VD',
  orderedOn: '8th Sept 2025',
  status: 'Low Stock',
  statusTone: 'warning',
  estimatedDelivery: '19th July 2025',
  totalAmount: 13450.32,
  shippingProgress: 82,
  origin: 'Shopsoma Warehouse',
  destination: 'Delivered',
  timeline: [
    {
      date: '8th Sept',
      time: '6:00AM',
      title: 'The order has been shipped',
      description: 'Distribution Center, Lagos',
    },
    {
      date: '6th Sept',
      time: '4:37PM',
      title: 'Item stock low. Please ship new stock',
      description: 'Shopsoma Warehouse, Lagos.',
      state: 'muted',
    },
    {
      date: '3rd Sept',
      time: '9:00AM',
      title: 'Order undergoing inspection',
      description: 'Shopsoma Warehouse, Lagos.',
      state: 'muted',
    },
    {
      date: '1st Sept',
      time: '8:34PM',
      title: 'Order placed',
      description: '',
      state: 'muted',
    },
  ] as TimelineEntry[],
  items: [
    {
      name: 'Goth raclette irony pbr&b it.',
      variant: 'XL, Red',
      price: 837,
      quantity: 1,
      status: 'low',
      image: '/images/demo-image-2.svg',
      stock: 12,
      size: 'XL',
      color: 'Maroon',
    },
    {
      name: 'Goth raclette irony pbr&b it.',
      variant: 'XL, Red',
      price: 837,
      quantity: 1,
      status: 'delayed',
      image: '/images/demo-image-3.svg',
      stock: 6,
      size: 'L',
      color: 'Cedar',
    },
    {
      name: 'Goth raclette irony pbr&b it.',
      variant: 'XL, Red',
      price: 837,
      quantity: 1,
      status: 'ok',
      image: '/images/demo-image-4.svg',
      stock: 18,
      size: 'M',
      color: 'Emerald',
    },
  ] as OrderItem[],
};

function formatCurrency(amount: number, currency = 'USD') {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency }).format(amount);
}

function StockBadge({ status }: { status: OrderItem['status'] }) {
  const styles =
    status === 'low'
      ? 'bg-[#FEF3E2] text-[#D97706]'
      : status === 'delayed'
      ? 'bg-rose-100 text-rose-700'
      : 'bg-emerald-100 text-emerald-700';

  const label =
    status === 'low' ? 'Low Stock' : status === 'delayed' ? 'Delayed' : 'In Stock';

  return (
    <span className={`px-3 py-1 rounded-full text-xs font-semibold ${styles}`}>
      {label}
    </span>
  );
}

function StatusPill({ label, tone = 'neutral' }: { label: string; tone?: 'success' | 'warning' | 'neutral' }) {
  const base = 'px-3 py-1 rounded-full text-xs font-semibold inline-flex items-center gap-2';
  if (tone === 'success') return <span className={`${base} bg-emerald-50 text-emerald-700`}>{label}</span>;
  if (tone === 'warning') return <span className={`${base} bg-amber-50 text-amber-700`}>{label}</span>;
  return <span className={`${base} bg-gray-100 text-gray-700`}>{label}</span>;
}

export default function VendorOrderDetail() {
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const { toasts, hideToast, error, success } = useToast();

  const [order, setOrder] = useState<VendorOrder | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedItem, setSelectedItem] = useState<VendorOrderItem | null>(null);
  const [statusSelection, setStatusSelection] = useState<string>('pending');
  const [updating, setUpdating] = useState(false);

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

  const handleEditItem = (item: VendorOrderItem) => {
    setSelectedItem(item);
    setStatusSelection(item.fulfillment_status);
  };

  const closeModal = () => setSelectedItem(null);

  const handleSaveStatus = async () => {
    if (!selectedItem || !order) return;

    try {
      setUpdating(true);
      await updateVendorOrderItem(order.id, selectedItem.id, statusSelection);

      // Update local state
      setOrder(prev => {
        if (!prev) return prev;
        return {
          ...prev,
          items: prev.items.map(item =>
            item.id === selectedItem.id
              ? { ...item, fulfillment_status: statusSelection }
              : item
          ),
        };
      });

      success('Order item status updated successfully', 'Updated');
      closeModal();
    } catch (err: any) {
      console.error('Failed to update order item', err);
      error(
        err.response?.data?.detail || 'Failed to update order item',
        'Update Failed'
      );
    } finally {
      setUpdating(false);
    }
  };

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

          {/* Top overview */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
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
                {order.items.map((item) => (
                  <div key={item.id} className="py-4 flex items-center gap-4">
                    <div className="h-16 w-16 rounded-xl bg-gray-100 flex items-center justify-center border border-gray-200">
                      <Package className="h-6 w-6 text-gray-400" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-semibold text-gray-900 line-clamp-1">{item.product_title}</p>
                      <p className="text-sm text-gray-700 mt-1">₦{item.unit_price.toFixed(2)} · Qty: {item.quantity}</p>
                      <p className="text-xs text-gray-500 mt-1">Payout: ₦{item.vendor_payout.toFixed(2)}</p>
                    </div>
                    <div className="flex items-center gap-3">
                      <button
                        type="button"
                        className="inline-flex items-center gap-2 px-3 py-2 text-sm font-medium text-gray-700 border border-gray-200 rounded-lg hover:bg-gray-50 transition"
                        onClick={() => handleEditItem(item)}
                      >
                        <Pencil className="w-4 h-4" />
                        Update
                      </button>
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
            </div>
          </div>
        </div>
      </div>

      {selectedItem && (
        <div className="fixed inset-0 bg-black/40 backdrop-blur-sm flex items-center justify-center z-50 px-4 py-8">
          <div className="bg-white rounded-2xl shadow-2xl max-w-3xl w-full overflow-hidden">
            <div className="p-6 space-y-4">
              <div className="flex items-start justify-between gap-3">
                <div className="space-y-1">
                  <p className="text-sm text-gray-500">₦{selectedItem.unit_price.toFixed(2)}</p>
                  <h3 className="text-lg font-semibold text-gray-900 leading-tight">{selectedItem.product_title}</h3>
                </div>
                <button
                  type="button"
                  onClick={closeModal}
                  className="text-gray-500 hover:text-gray-700"
                  aria-label="Close edit modal"
                  disabled={updating}
                >
                  <X className="w-5 h-5" />
                </button>
              </div>

              <div className="grid grid-cols-2 gap-3 text-sm text-gray-800">
                <div className="flex justify-between py-2 border-b border-gray-100">
                  <span className="text-gray-500">Quantity</span>
                  <span className="font-semibold">{selectedItem.quantity}</span>
                </div>
                <div className="flex justify-between py-2 border-b border-gray-100">
                  <span className="text-gray-500">Subtotal</span>
                  <span className="font-semibold">₦{selectedItem.subtotal.toFixed(2)}</span>
                </div>
                <div className="flex justify-between py-2 border-b border-gray-100">
                  <span className="text-gray-500">Your Payout</span>
                  <span className="font-semibold">₦{selectedItem.vendor_payout.toFixed(2)}</span>
                </div>
                <div className="flex justify-between py-2 border-b border-gray-100">
                  <span className="text-gray-500">Current Status</span>
                  <span className="font-semibold capitalize">{selectedItem.fulfillment_status.replace('_', ' ')}</span>
                </div>
              </div>

              <div className="space-y-2">
                <p className="text-xs text-gray-500 uppercase tracking-[0.2em]">Update Fulfillment Status</p>
                <div className="flex flex-wrap gap-2">
                  {(['pending', 'processing', 'shipped', 'delivered', 'cancelled']).map((status) => {
                    const isActive = statusSelection === status;
                    const colors =
                      status === 'pending'
                        ? 'bg-amber-50 text-amber-700 border-amber-100'
                        : status === 'processing'
                        ? 'bg-blue-50 text-blue-700 border-blue-100'
                        : status === 'shipped'
                        ? 'bg-purple-50 text-purple-700 border-purple-100'
                        : status === 'delivered'
                        ? 'bg-emerald-50 text-emerald-700 border-emerald-100'
                        : 'bg-emerald-50 text-emerald-700 border-emerald-100';
                    return (
                      <button
                        key={status}
                        type="button"
                        onClick={() => setStatusSelection(status)}
                        disabled={updating}
                        className={`px-3 py-1.5 rounded-full text-xs font-semibold border transition disabled:opacity-50 ${
                          isActive ? colors + ' ring-2 ring-offset-1 ring-gray-100' : 'bg-gray-100 text-gray-700 border-gray-200'
                        }`}
                      >
                        {status.charAt(0).toUpperCase() + status.slice(1)}
                      </button>
                    );
                  })}
                </div>
              </div>

              <div className="flex items-center gap-3 pt-4">
                <button
                  type="button"
                  className="flex-1 px-4 py-3 border border-gray-300 text-gray-700 font-semibold rounded-lg hover:bg-gray-50 transition disabled:opacity-50"
                  onClick={closeModal}
                  disabled={updating}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  className="flex-1 bg-[#105E53] text-white font-semibold rounded-lg py-3 hover:bg-[#0c4c45] transition disabled:opacity-50 inline-flex items-center justify-center gap-2"
                  onClick={handleSaveStatus}
                  disabled={updating}
                >
                  {updating ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Updating...
                    </>
                  ) : (
                    <>
                      <CheckCircle2 className="h-4 w-4" />
                      Update Status
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      <ToastContainer toasts={toasts} onDismiss={hideToast} />
    </div>
  );
}
