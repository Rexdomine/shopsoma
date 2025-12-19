/**
 * Order Filters Component
 * Filter controls for admin order list
 */
import { useState, useEffect } from 'react';
import type {
  OrderFilterParams,
  PaymentStatus,
  FulfillmentStatus,
} from '../../services/adminOrderService';

interface OrderFiltersProps {
  onFilterChange: (filters: OrderFilterParams) => void;
  loading?: boolean;
}

export default function OrderFilters({ onFilterChange, loading }: OrderFiltersProps) {
  const [search, setSearch] = useState('');
  const [paymentStatus, setPaymentStatus] = useState<PaymentStatus | ''>('');
  const [fulfillmentStatus, setFulfillmentStatus] = useState<FulfillmentStatus | ''>('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [showFilters, setShowFilters] = useState(false);

  // Apply filters when they change
  useEffect(() => {
    const filters: OrderFilterParams = {};

    if (search.trim()) filters.search = search.trim();
    if (paymentStatus) filters.payment_status = paymentStatus as PaymentStatus;
    if (fulfillmentStatus) filters.fulfillment_status = fulfillmentStatus as FulfillmentStatus;
    if (dateFrom) filters.date_from = dateFrom;
    if (dateTo) filters.date_to = dateTo;

    onFilterChange(filters);
  }, [search, paymentStatus, fulfillmentStatus, dateFrom, dateTo, onFilterChange]);

  const handleReset = () => {
    setSearch('');
    setPaymentStatus('');
    setFulfillmentStatus('');
    setDateFrom('');
    setDateTo('');
  };

  const hasActiveFilters =
    search || paymentStatus || fulfillmentStatus || dateFrom || dateTo;

  return (
    <div className="bg-white rounded-lg shadow p-6 mb-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-gray-900">Filters</h3>
        <div className="flex items-center gap-3">
          {hasActiveFilters && (
            <button
              onClick={handleReset}
              className="text-sm text-gray-600 hover:text-gray-900"
              disabled={loading}
            >
              Clear all
            </button>
          )}
          <button
            onClick={() => setShowFilters(!showFilters)}
            className="text-[#105E53] hover:text-[#0d4a41] font-medium text-sm"
          >
            {showFilters ? 'Hide filters' : 'Show filters'}
          </button>
        </div>
      </div>

      {/* Search Bar (Always Visible) */}
      <div className="mb-4">
        <input
          type="text"
          placeholder="Search by order number, customer name, or email..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          disabled={loading}
          className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-[#105E53] focus:border-transparent"
        />
      </div>

      {/* Advanced Filters */}
      {showFilters && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {/* Payment Status */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Payment Status
            </label>
            <select
              value={paymentStatus}
              onChange={(e) => setPaymentStatus(e.target.value as PaymentStatus | '')}
              disabled={loading}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-[#105E53] focus:border-transparent"
            >
              <option value="">All payments</option>
              <option value="pending">Pending</option>
              <option value="paid">Paid</option>
              <option value="failed">Failed</option>
              <option value="refunded">Refunded</option>
            </select>
          </div>

          {/* Fulfillment Status */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Fulfillment Status
            </label>
            <select
              value={fulfillmentStatus}
              onChange={(e) => setFulfillmentStatus(e.target.value as FulfillmentStatus | '')}
              disabled={loading}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-[#105E53] focus:border-transparent"
            >
              <option value="">All orders</option>
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

          {/* Date From */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Date From
            </label>
            <input
              type="date"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
              disabled={loading}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-[#105E53] focus:border-transparent"
            />
          </div>

          {/* Date To */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Date To
            </label>
            <input
              type="date"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
              disabled={loading}
              min={dateFrom}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-[#105E53] focus:border-transparent"
            />
          </div>
        </div>
      )}

      {/* Active Filters Display */}
      {hasActiveFilters && (
        <div className="mt-4 flex flex-wrap gap-2">
          {search && (
            <span className="inline-flex items-center gap-1 px-3 py-1 bg-gray-100 text-gray-700 rounded-full text-sm">
              Search: "{search}"
              <button
                onClick={() => setSearch('')}
                className="hover:text-gray-900"
                disabled={loading}
              >
                ×
              </button>
            </span>
          )}
          {paymentStatus && (
            <span className="inline-flex items-center gap-1 px-3 py-1 bg-blue-100 text-blue-700 rounded-full text-sm">
              Payment: {paymentStatus}
              <button
                onClick={() => setPaymentStatus('')}
                className="hover:text-blue-900"
                disabled={loading}
              >
                ×
              </button>
            </span>
          )}
          {fulfillmentStatus && (
            <span className="inline-flex items-center gap-1 px-3 py-1 bg-purple-100 text-purple-700 rounded-full text-sm">
              Status: {fulfillmentStatus}
              <button
                onClick={() => setFulfillmentStatus('')}
                className="hover:text-purple-900"
                disabled={loading}
              >
                ×
              </button>
            </span>
          )}
          {dateFrom && (
            <span className="inline-flex items-center gap-1 px-3 py-1 bg-green-100 text-green-700 rounded-full text-sm">
              From: {dateFrom}
              <button
                onClick={() => setDateFrom('')}
                className="hover:text-green-900"
                disabled={loading}
              >
                ×
              </button>
            </span>
          )}
          {dateTo && (
            <span className="inline-flex items-center gap-1 px-3 py-1 bg-green-100 text-green-700 rounded-full text-sm">
              To: {dateTo}
              <button
                onClick={() => setDateTo('')}
                className="hover:text-green-900"
                disabled={loading}
              >
                ×
              </button>
            </span>
          )}
        </div>
      )}
    </div>
  );
}
