/**
 * Admin Orders Page
 * Main order management page for admin dashboard
 */
import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { useNavigate, useLocation, useSearchParams } from 'react-router-dom';
import AdminSidebar from '../../components/admin/AdminSidebar';
import CurrencySwitcher from '../../components/common/CurrencySwitcher';
import OrderStats from '../../components/admin/OrderStats';
import OrderFilters from '../../components/admin/OrderFilters';
import BulkOrderActions from '../../components/admin/BulkOrderActions';
import { useToast } from '../../hooks/useToast';
import { useCurrency } from '../../hooks/useCurrency';
import { formatPriceWithConversion } from '../../utils/pricing';
import {
  getOrderStats,
  listOrders,
  bulkUpdateStatus,
  exportOrdersCSV,
  downloadCSV,
} from '../../services/adminOrderService';
import type {
  OrderFilterParams,
  OrderListItem,
  OrderStats as OrderStatsType,
  FulfillmentStatus,
  PaymentStatus,
} from '../../services/adminOrderService';
import { getAdminStatusLabel } from '../../utils/orderStatusMessages';

export type PaymentScopeTab = 'paid' | 'pending' | 'failed' | 'refunded' | 'all';

interface TabDefinition {
  id: PaymentScopeTab;
  label: string;
  badge?: (stats: OrderStatsType | null) => number | undefined;
}

const TABS: TabDefinition[] = [
  { id: 'paid', label: 'Orders Received', badge: (stats) => stats?.total_orders },
  { id: 'pending', label: 'Pending Payments', badge: (stats) => stats?.pending_payment },
  { id: 'failed', label: 'Failed Payments', badge: (stats) => stats?.failed_payment },
  { id: 'refunded', label: 'Refunded' },
  { id: 'all', label: 'All Orders' },
];

export default function AdminOrders() {
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const { toasts, hideToast, success, error, warning } = useToast();
  const { currentCurrency, setCurrency, exchangeRates } = useCurrency();

  const [stats, setStats] = useState<OrderStatsType | null>(null);
  const [orders, setOrders] = useState<OrderListItem[]>([]);
  const [selectedOrderIds, setSelectedOrderIds] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [statsLoading, setStatsLoading] = useState(true);
  const [exporting, setExporting] = useState(false);

  // Pagination
  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);
  const [totalPages, setTotalPages] = useState(0);
  const [total, setTotal] = useState(0);

  // Scope: defaults to 'paid' (Orders Received)
  const initialScope = useMemo<PaymentScopeTab>(() => {
    const raw = searchParams.get('payment_status')?.toLowerCase();
    if (raw === 'pending' || raw === 'failed' || raw === 'refunded' || raw === 'all') {
      return raw;
    }
    return 'paid';
  }, [searchParams]);

  const [selectedScope, setSelectedScope] = useState<PaymentScopeTab>(initialScope);
  const selectedScopeRef = useRef(selectedScope);
  selectedScopeRef.current = selectedScope;

  // Filters (always scoping by payment_status)
  const [filters, setFilters] = useState<OrderFilterParams>({
    payment_status: initialScope,
  });

  const formatOrderAmount = (amount: number, sourceCurrency: 'NGN' | 'USD') =>
    formatPriceWithConversion(amount, sourceCurrency, currentCurrency, exchangeRates);

  // Sync selectedScope with URL changes
  useEffect(() => {
    const raw = searchParams.get('payment_status')?.toLowerCase();
    const targetScope: PaymentScopeTab =
      raw === 'pending' || raw === 'failed' || raw === 'refunded' || raw === 'all'
        ? raw
        : 'paid';

    setSelectedScope((current) => {
      if (current !== targetScope) {
        setPage(1);
        setSelectedOrderIds([]);
        setFilters((prev) => ({
          ...prev,
          payment_status: targetScope,
        }));
        return targetScope;
      }
      return current;
    });
  }, [searchParams]);

  // Load statistics
  const loadStats = useCallback(async () => {
    try {
      setStatsLoading(true);
      const data = await getOrderStats();
      setStats(data);
    } catch (err) {
      console.error('Failed to load stats:', err);
      error('Failed to load order statistics');
    } finally {
      setStatsLoading(false);
    }
  }, [error]);

  // Load orders
  const loadOrders = useCallback(async () => {
    try {
      setLoading(true);
      const data = await listOrders({
        page,
        page_size: pageSize,
        ...filters,
        payment_status: selectedScope,
      });

      setOrders(data.orders);
      setTotal(data.total);
      setTotalPages(data.total_pages);
    } catch (err) {
      console.error('Failed to load orders:', err);
      error('Failed to load orders');
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, filters, selectedScope, error]);

  // Initial load
  useEffect(() => {
    loadStats();
  }, [loadStats]);

  useEffect(() => {
    loadOrders();
  }, [loadOrders]);

  // Handle scope / tab change
  const handleScopeChange = useCallback(
    (newScope: PaymentScopeTab) => {
      if (newScope === selectedScopeRef.current) return;
      setSelectedScope(newScope);
      setPage(1);
      setSelectedOrderIds([]);
      setFilters((prev) => ({
        ...prev,
        payment_status: newScope,
      }));
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        if (newScope === 'paid') {
          next.delete('payment_status');
        } else {
          next.set('payment_status', newScope);
        }
        return next;
      });
    },
    [setSearchParams]
  );

  // Handle filter change
  const handleFilterChange = useCallback(
    (newFilters: OrderFilterParams) => {
      const currentScope = selectedScopeRef.current;
      const nextScope = (newFilters.payment_status || currentScope) as PaymentScopeTab;
      if (nextScope !== currentScope) {
        setSelectedScope(nextScope);
        setSearchParams((prev) => {
          const next = new URLSearchParams(prev);
          if (nextScope === 'paid') {
            next.delete('payment_status');
          } else {
            next.set('payment_status', nextScope);
          }
          return next;
        });
      }
      setFilters({
        ...newFilters,
        payment_status: nextScope,
      });
      setPage(1);
    },
    [setSearchParams]
  );

  // Handle bulk update
  const handleBulkUpdate = async (status: FulfillmentStatus, notes?: string) => {
    try {
      const result = await bulkUpdateStatus({
        order_ids: selectedOrderIds,
        fulfillment_status: status,
        admin_notes: notes,
      });

      success(result.message);
      setSelectedOrderIds([]);
    } catch (err) {
      console.error('Bulk update failed:', err);
      error('Failed to update orders');
      return;
    }
    try {
      await loadOrders();
      await loadStats();
    } catch (err) {
      console.error('Failed to refresh orders:', err);
      warning('Orders updated, but failed to refresh list');
    }
  };

  // Handle select all
  const handleSelectAll = () => {
    if (selectedOrderIds.length === orders.length) {
      setSelectedOrderIds([]);
    } else {
      setSelectedOrderIds(orders.map((order) => order.id));
    }
  };

  // Handle select one
  const handleSelectOrder = (orderId: string) => {
    if (selectedOrderIds.includes(orderId)) {
      setSelectedOrderIds(selectedOrderIds.filter((id) => id !== orderId));
    } else {
      setSelectedOrderIds([...selectedOrderIds, orderId]);
    }
  };

  // Handle export
  const handleExport = async () => {
    try {
      setExporting(true);
      const exportParams = {
        ...filters,
        payment_status: selectedScope,
      };
      const blob = await exportOrdersCSV(exportParams);
      downloadCSV(blob, `orders_${selectedScope}_${new Date().toISOString().split('T')[0]}.csv`);
      success('Orders exported successfully');
    } catch (err) {
      console.error('Export failed:', err);
      error('Failed to export orders');
    } finally {
      setExporting(false);
    }
  };

  // Get status badge color
  const getStatusColor = (status: FulfillmentStatus): string => {
    const colors: Record<FulfillmentStatus, string> = {
      order_received: 'bg-blue-100 text-blue-800',
      preparing_for_pickup: 'bg-yellow-100 text-yellow-800',
      pickup_scheduled: 'bg-purple-100 text-purple-800',
      picked_up: 'bg-indigo-100 text-indigo-800',
      in_transit: 'bg-cyan-100 text-cyan-800',
      out_for_delivery: 'bg-orange-100 text-orange-800',
      delivered: 'bg-green-100 text-green-800',
      delivery_failed: 'bg-red-100 text-red-800',
      returned: 'bg-gray-100 text-gray-800',
      cancelled: 'bg-red-100 text-red-800',
    };
    return colors[status] || 'bg-gray-100 text-gray-800';
  };

  const getPaymentColor = (status: PaymentStatus): string => {
    const colors: Record<PaymentStatus, string> = {
      pending: 'bg-amber-100 text-amber-800',
      paid: 'bg-green-100 text-green-800',
      failed: 'bg-red-100 text-red-800',
      refunded: 'bg-gray-100 text-gray-800',
    };
    return colors[status] || 'bg-gray-100 text-gray-800';
  };

  return (
    <div className="min-h-screen bg-[var(--color-page-bg)] flex flex-col md:flex-row w-full overflow-x-hidden">
      <AdminSidebar activeSection={selectedScope === 'pending' ? 'orders-pending' : 'orders'} />

      <main className="min-w-0 flex-1 p-4 sm:p-6 lg:p-8 space-y-6">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6 sm:mb-8">
          <div>
            <h1 className="text-2xl sm:text-3xl font-bold text-gray-900">
              {selectedScope === 'pending'
                ? 'Pending Payments'
                : selectedScope === 'paid'
                ? 'Orders Received'
                : selectedScope === 'failed'
                ? 'Failed Payments'
                : selectedScope === 'refunded'
                ? 'Refunded Orders'
                : 'Order Management'}
            </h1>
            <p className="mt-1 text-sm text-gray-500">
              {selectedScope === 'pending'
                ? 'Orders created at checkout awaiting Paystack payment confirmation'
                : selectedScope === 'paid'
                ? 'Confirmed and paid customer orders ready for fulfillment'
                : selectedScope === 'failed'
                ? 'Orders with unsuccessful payment attempts'
                : selectedScope === 'refunded'
                ? 'Orders that have been refunded to customers'
                : 'Manage and track all orders across vendors'}
            </p>
          </div>
          <div className="flex items-center gap-3 flex-wrap">
            <CurrencySwitcher value={currentCurrency} onChange={setCurrency} />
            <button
              onClick={handleExport}
              disabled={exporting || loading}
              className="px-4 py-2 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50 transition-colors flex items-center gap-2 text-sm"
            >
              📥 {exporting ? 'Exporting...' : 'Export CSV'}
            </button>
          </div>
        </div>

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
              <button
                onClick={() => hideToast(toast.id)}
                className="text-white hover:text-gray-200"
              >
                ×
              </button>
            </div>
          </div>
        ))}

        {/* Statistics */}
        <OrderStats
          stats={stats}
          loading={statsLoading}
          onSelectPaymentStatus={(scope) => handleScopeChange(scope as PaymentScopeTab)}
        />

        {/* Navigation View Tabs */}
        <div className="border-b border-gray-200">
          <nav className="-mb-px flex space-x-2 sm:space-x-4 overflow-x-auto pb-1" aria-label="Order Views">
            {TABS.map((tab) => {
              const isActive = selectedScope === tab.id;
              const count = tab.badge ? tab.badge(stats) : undefined;
              return (
                <button
                  key={tab.id}
                  onClick={() => handleScopeChange(tab.id)}
                  className={`whitespace-nowrap py-2.5 px-4 rounded-t-lg font-medium text-sm flex items-center gap-2 border-b-2 transition-colors ${
                    isActive
                      ? 'border-[#105E53] text-[#105E53] bg-white font-semibold'
                      : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                  }`}
                  aria-current={isActive ? 'page' : undefined}
                >
                  <span>{tab.label}</span>
                  {count !== undefined && (
                    <span
                      className={`text-xs px-2 py-0.5 rounded-full ${
                        isActive
                          ? 'bg-[#105E53]/10 text-[#105E53] font-bold'
                          : tab.id === 'pending' && count > 0
                          ? 'bg-amber-100 text-amber-800 font-semibold'
                          : tab.id === 'failed' && count > 0
                          ? 'bg-red-100 text-red-800 font-semibold'
                          : 'bg-gray-100 text-gray-600'
                      }`}
                    >
                      {count}
                    </span>
                  )}
                </button>
              );
            })}
          </nav>
        </div>

        {/* Filters */}
        <OrderFilters
          onFilterChange={handleFilterChange}
          loading={loading}
          activePaymentStatus={selectedScope}
          onPaymentStatusChange={(scope) => handleScopeChange(scope as PaymentScopeTab)}
        />

        {/* Bulk Actions */}
        <BulkOrderActions
          selectedOrderIds={selectedOrderIds}
          onBulkUpdate={handleBulkUpdate}
          onClearSelection={() => setSelectedOrderIds([])}
          loading={loading}
        />

        {/* Orders Table */}
        <div className="bg-white rounded-lg shadow overflow-hidden">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left">
                    <input
                      type="checkbox"
                      checked={orders.length > 0 && selectedOrderIds.length === orders.length}
                      onChange={handleSelectAll}
                      disabled={loading || orders.length === 0}
                      className="rounded border-gray-300 text-[#105E53] focus:ring-[#105E53]"
                    />
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Order
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Customer
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Amount
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Payment
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Status
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Details
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Date
                  </th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {loading ? (
                  <tr>
                    <td colSpan={9} className="px-6 py-12 text-center text-gray-500">
                      Loading orders...
                    </td>
                  </tr>
                ) : orders.length === 0 ? (
                  <tr>
                    <td colSpan={9} className="px-6 py-12 text-center text-gray-500">
                      {selectedScope === 'pending'
                        ? 'No pending payments found'
                        : selectedScope === 'paid'
                        ? 'No orders received yet'
                        : selectedScope === 'failed'
                        ? 'No failed payments found'
                        : selectedScope === 'refunded'
                        ? 'No refunded orders found'
                        : 'No orders found'}
                    </td>
                  </tr>
                ) : (
                  orders.map((order) => (
                    <tr key={order.id} className="hover:bg-gray-50">
                      <td className="px-6 py-4">
                        <input
                          type="checkbox"
                          checked={selectedOrderIds.includes(order.id)}
                          onChange={() => handleSelectOrder(order.id)}
                          className="rounded border-gray-300 text-[#105E53] focus:ring-[#105E53]"
                        />
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <div className="text-sm font-medium text-gray-900">
                          {order.order_number}
                        </div>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <div className="text-sm text-gray-900">
                          {order.customer.first_name} {order.customer.last_name}
                        </div>
                        <div className="text-sm text-gray-500">{order.customer.email}</div>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <div className="text-sm font-medium text-gray-900">
                          {formatOrderAmount(order.total_amount, order.currency)}
                        </div>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <span
                          className={`px-2.5 py-1 inline-flex text-xs leading-5 font-semibold rounded-full capitalize ${getPaymentColor(
                            order.payment_status
                          )}`}
                        >
                          {order.payment_status}
                        </span>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <span
                          className={`px-2.5 py-1 inline-flex text-xs leading-5 font-semibold rounded-full ${
                            order.payment_status === 'pending'
                              ? 'bg-amber-100 text-amber-800 border border-amber-200'
                              : order.payment_status === 'failed'
                              ? 'bg-red-100 text-red-800 border border-red-200'
                              : order.payment_status === 'refunded'
                              ? 'bg-gray-100 text-gray-800 border border-gray-200'
                              : getStatusColor(order.fulfillment_status)
                          }`}
                        >
                          {order.payment_status === 'pending'
                            ? 'Awaiting Payment'
                            : order.payment_status === 'failed'
                            ? 'Payment Failed'
                            : order.payment_status === 'refunded'
                            ? 'Payment Refunded'
                            : getAdminStatusLabel(order.fulfillment_status)}
                        </span>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                        <div>{order.vendor_count} vendor(s)</div>
                        <div>{order.item_count} item(s)</div>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                        {new Date(order.created_at).toLocaleDateString()}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                        <button
                          onClick={() =>
                            navigate(`/admin/orders/${order.id}`, {
                              state: { from: location.pathname + location.search },
                            })
                          }
                          className="text-[#105E53] hover:text-[#0d4a41]"
                        >
                          View →
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="bg-white px-4 py-3 border-t border-gray-200 sm:px-6">
              <div className="flex items-center justify-between">
                <div className="flex-1 flex justify-between sm:hidden">
                  <button
                    onClick={() => setPage(Math.max(1, page - 1))}
                    disabled={page === 1 || loading}
                    className="relative inline-flex items-center px-4 py-2 border border-gray-300 text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 disabled:opacity-50"
                  >
                    Previous
                  </button>
                  <button
                    onClick={() => setPage(Math.min(totalPages, page + 1))}
                    disabled={page === totalPages || loading}
                    className="ml-3 relative inline-flex items-center px-4 py-2 border border-gray-300 text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 disabled:opacity-50"
                  >
                    Next
                  </button>
                </div>
                <div className="hidden sm:flex-1 sm:flex sm:items-center sm:justify-between">
                  <div>
                    <p className="text-sm text-gray-700">
                      Showing <span className="font-medium">{(page - 1) * pageSize + 1}</span> to{' '}
                      <span className="font-medium">
                        {Math.min(page * pageSize, total)}
                      </span>{' '}
                      of <span className="font-medium">{total}</span> results
                    </p>
                  </div>
                  <div>
                    <nav className="relative z-0 inline-flex rounded-md shadow-sm -space-x-px">
                      <button
                        onClick={() => setPage(Math.max(1, page - 1))}
                        disabled={page === 1 || loading}
                        className="relative inline-flex items-center px-2 py-2 rounded-l-md border border-gray-300 bg-white text-sm font-medium text-gray-500 hover:bg-gray-50 disabled:opacity-50"
                      >
                        Previous
                      </button>
                      {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                        const pageNum = i + 1;
                        return (
                          <button
                            key={pageNum}
                            onClick={() => setPage(pageNum)}
                            disabled={loading}
                            className={`relative inline-flex items-center px-4 py-2 border text-sm font-medium ${
                              page === pageNum
                                ? 'z-10 bg-[#105E53] border-[#105E53] text-white'
                                : 'bg-white border-gray-300 text-gray-500 hover:bg-gray-50'
                            }`}
                          >
                            {pageNum}
                          </button>
                        );
                      })}
                      <button
                        onClick={() => setPage(Math.min(totalPages, page + 1))}
                        disabled={page === totalPages || loading}
                        className="relative inline-flex items-center px-2 py-2 rounded-r-md border border-gray-300 bg-white text-sm font-medium text-gray-500 hover:bg-gray-50 disabled:opacity-50"
                      >
                        Next
                      </button>
                    </nav>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
