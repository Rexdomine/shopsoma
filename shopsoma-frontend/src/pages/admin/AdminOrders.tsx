/**
 * Admin Orders Page
 * Main order management page for admin dashboard
 */
import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import AdminSidebar from '../../components/admin/AdminSidebar';
import OrderStats from '../../components/admin/OrderStats';
import OrderFilters from '../../components/admin/OrderFilters';
import BulkOrderActions from '../../components/admin/BulkOrderActions';
import { useToast } from '../../hooks/useToast';
import { useCurrency } from '../../hooks/useCurrency';
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

export default function AdminOrders() {
  const navigate = useNavigate();
  const { toasts, hideToast, success, error } = useToast();
  const { formatPrice } = useCurrency();

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

  // Filters
  const [filters, setFilters] = useState<OrderFilterParams>({});

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
  }, [page, pageSize, filters, error]);

  // Initial load
  useEffect(() => {
    loadStats();
  }, [loadStats]);

  useEffect(() => {
    loadOrders();
  }, [loadOrders]);

  // Handle filter change
  const handleFilterChange = useCallback((newFilters: OrderFilterParams) => {
    setFilters(newFilters);
    setPage(1); // Reset to first page
  }, []);

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
      await loadOrders();
      await loadStats();
    } catch (err) {
      console.error('Bulk update failed:', err);
      error('Failed to update orders');
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
      const blob = await exportOrdersCSV(filters);
      downloadCSV(blob, `orders_${new Date().toISOString().split('T')[0]}.csv`);
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
    <div className="min-h-screen bg-[#F9FAFB] flex">
      <AdminSidebar activeSection="orders" />

      <main className="flex-1 p-8 space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-3xl font-bold text-gray-900">Order Management</h1>
            <p className="mt-1 text-sm text-gray-500">
              Manage and track all orders across vendors
            </p>
          </div>
          <button
            onClick={handleExport}
            disabled={exporting || loading}
            className="px-4 py-2 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50 transition-colors flex items-center gap-2"
          >
            📥 {exporting ? 'Exporting...' : 'Export CSV'}
          </button>
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
        <OrderStats stats={stats} loading={statsLoading} />

        {/* Filters */}
        <OrderFilters onFilterChange={handleFilterChange} loading={loading} />

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
                      No orders found
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
                          {formatPrice(order.total_amount)}
                        </div>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <span
                          className={`px-2 py-1 inline-flex text-xs leading-5 font-semibold rounded-full ${getPaymentColor(
                            order.payment_status
                          )}`}
                        >
                          {order.payment_status}
                        </span>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <span
                          className={`px-2 py-1 inline-flex text-xs leading-5 font-semibold rounded-full ${getStatusColor(
                            order.fulfillment_status
                          )}`}
                        >
                          {getAdminStatusLabel(order.fulfillment_status)}
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
                          onClick={() => navigate(`/admin/orders/${order.id}`)}
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
