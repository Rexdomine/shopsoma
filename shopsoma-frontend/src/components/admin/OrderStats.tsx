/**
 * Order Statistics Component
 * Display order metrics for admin dashboard
 */
import type { OrderStats as OrderStatsType } from '../../services/adminOrderService';
import { useCurrency } from '../../hooks/useCurrency';

interface OrderStatsProps {
  stats: OrderStatsType | null;
  loading?: boolean;
}

interface StatCard {
  label: string;
  value: string | number;
  subtext?: string;
  color: string;
  icon: string;
}

function OrderStatsComponent({ stats, loading }: OrderStatsProps) {
  const { formatBasePrice } = useCurrency();

  if (loading) {
    return (
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 sm:gap-6 mb-8">
        {[1, 2, 3, 4, 5, 6, 7, 8].map((i) => (
          <div key={i} className="bg-white rounded-lg shadow p-4 sm:p-6 animate-pulse min-w-0">
            <div className="h-4 bg-gray-200 rounded w-24 mb-2"></div>
            <div className="h-8 bg-gray-200 rounded w-32 mb-1"></div>
            <div className="h-3 bg-gray-200 rounded w-20"></div>
          </div>
        ))}
      </div>
    );
  }

  if (!stats) {
    return null;
  }

  const statCards: StatCard[] = [
    {
      label: 'Total Revenue',
      value: formatBasePrice(stats.total_revenue),
      subtext: `${stats.total_orders} orders`,
      color: 'text-green-600',
      icon: '💰',
    },
    {
      label: 'Average Order',
      value: formatBasePrice(stats.average_order_value),
      subtext: 'Per order',
      color: 'text-blue-600',
      icon: '📊',
    },
    {
      label: 'Today',
      value: formatBasePrice(stats.revenue_today),
      subtext: `${stats.orders_today} orders`,
      color: 'text-purple-600',
      icon: '📅',
    },
    {
      label: 'Orders Received',
      value: stats.pending_orders,
      subtext: 'Paid & awaiting processing',
      color: 'text-yellow-600',
      icon: '⏳',
    },
    {
      label: 'Processing',
      value: stats.processing_orders,
      subtext: 'Being prepared',
      color: 'text-orange-600',
      icon: '📦',
    },
    {
      label: 'Shipped',
      value: stats.shipped_orders,
      subtext: 'In transit',
      color: 'text-blue-600',
      icon: '🚚',
    },
    {
      label: 'Delivered',
      value: stats.delivered_orders,
      subtext: 'Completed',
      color: 'text-green-600',
      icon: '✅',
    },
    {
      label: 'Cancelled',
      value: stats.cancelled_orders,
      subtext: 'Cancelled orders',
      color: 'text-red-600',
      icon: '❌',
    },
  ];

  return (
    <div>
      <h2 className="text-lg font-semibold text-gray-900 mb-4">Order Statistics</h2>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 sm:gap-6 mb-8">
        {statCards.map((card, index) => (
          <div
            key={index}
            className="bg-white rounded-lg shadow hover:shadow-md transition-shadow p-4 sm:p-6 min-w-0"
          >
            <div className="flex items-start justify-between gap-2 mb-2 min-w-0">
              <span className="text-sm font-medium text-gray-600 truncate">{card.label}</span>
              <span className="text-2xl shrink-0">{card.icon}</span>
            </div>
            <div
              className={`text-xl sm:text-2xl font-bold ${card.color} mb-1 truncate`}
              title={String(card.value)}
            >
              {card.value}
            </div>
            {card.subtext && (
              <div className="text-xs text-gray-500 truncate">{card.subtext}</div>
            )}
          </div>
        ))}
      </div>

      {/* Payment Status Info */}
      {(stats.pending_payment > 0 || stats.failed_payment > 0) && (
        <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 mb-6">
          <div className="flex flex-col sm:flex-row sm:items-start gap-3">
            <span className="text-amber-600 text-xl shrink-0">⚠️</span>
            <div className="flex-1 min-w-0">
              <h3 className="font-medium text-amber-900 mb-1">Payment Attention Required</h3>
              <p className="text-sm text-amber-700 flex flex-wrap gap-x-4 gap-y-1">
                {stats.pending_payment > 0 && (
                  <span>
                    <strong>{stats.pending_payment}</strong> orders with pending payment
                  </span>
                )}
                {stats.failed_payment > 0 && (
                  <span>
                    <strong>{stats.failed_payment}</strong> orders with failed payment
                  </span>
                )}
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default OrderStatsComponent;
