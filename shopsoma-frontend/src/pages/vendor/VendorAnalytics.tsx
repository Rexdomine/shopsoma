import {
  Calendar,
  ChevronDown,
  Eye,
  Filter,
  Search,
  TrendingUp,
  Upload,
  ShoppingBag,
  Heart,
  UserCheck,
  UserPlus,
} from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import VendorSidebar from '../../components/vendor/VendorSidebar';
import CurrencySwitcher from '../../components/common/CurrencySwitcher';
import { useCurrencyStore } from '../../store/currencyStore';
import { formatPriceWithConversion } from '../../utils/pricing';
import { useNavigate } from 'react-router-dom';
import { ROUTES } from '../../config/constants';
import {
  vendorService,
  type VendorAnalyticsChartPoint,
  type VendorAnalyticsStats,
  type VendorAnalyticsSummary,
  type VendorEarningsItemsResponse,
  type VendorEarningsProductRow,
  type VendorEarningsOrderRow,
  type EarningsViewMode,
} from '../../services/vendorService';

type ViewMode = EarningsViewMode;

type AnalyticsRow = VendorEarningsProductRow | VendorEarningsOrderRow;

const getRangeStart = (end: Date, range: string) => {
  const start = new Date(end);
  if (range === '1D') {
    start.setDate(end.getDate() - 1);
  } else if (range === '7D') {
    start.setDate(end.getDate() - 7);
  } else if (range === '1M') {
    start.setMonth(end.getMonth() - 1);
  } else {
    start.setFullYear(end.getFullYear() - 1);
  }
  return start;
};

const formatAxisLabel = (timestamp: string, range: string) => {
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) {
    return '--';
  }
  if (range === '1D') {
    return date.toLocaleTimeString('en-US', { hour: 'numeric' });
  }
  if (range === '7D' || range === '1M') {
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  }
  return date.toLocaleDateString('en-US', { month: 'short' });
};

function StatusPill({ status }: { status: string }) {
  return (
    <span className="px-4 py-1 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700">
      {status}
    </span>
  );
}

function AnalyticsChart({
  data,
  formatAmount,
}: {
  data: VendorAnalyticsChartPoint[];
  formatAmount: (amount: number) => string;
}) {
  const width = 760;
  const height = 220;
  const padding = 24;
  const values = data.map((point) => point.revenue);
  const maxValue = Math.max(1, ...values);
  const minValue = 0;
  const rangeValue = Math.max(1, maxValue - minValue);
  const xStep = data.length > 1 ? (width - padding * 2) / (data.length - 1) : 0;
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);

  const points = data.map((point, index) => {
    const x = padding + index * xStep;
    const y =
      height -
      padding -
      ((point.revenue - minValue) / rangeValue) * (height - padding * 2);
    return { x, y };
  });

  const linePath = points
    .map((point, index) => `${index === 0 ? 'M' : 'L'}${point.x},${point.y}`)
    .join(' ');

  const areaPath = `${linePath} L${points[points.length - 1]?.x || 0},${
    height - padding
  } L${points[0]?.x || 0},${height - padding} Z`;

  const yTicks = 6;
  const yStep = (height - padding * 2) / yTicks;
  const yLabels = Array.from({ length: yTicks + 1 }).map((_, idx) => {
    const value = Math.round((maxValue / yTicks) * (yTicks - idx));
    return { value, y: padding + idx * yStep };
  });

  return (
    <div className="relative">
      {hoveredIndex !== null && data[hoveredIndex] && points[hoveredIndex] && (
        <div
          className="absolute bg-white border border-gray-200 rounded-2xl shadow-lg px-4 py-3 text-sm text-gray-700"
          style={{
            left: `${(points[hoveredIndex].x / width) * 100}%`,
            top: `${(points[hoveredIndex].y / height) * 100}%`,
            transform: 'translate(-50%, -110%)',
            minWidth: '220px',
          }}
        >
          <div className="flex items-center gap-2 text-gray-600 font-semibold">
            <Calendar className="h-4 w-4 text-gray-400" />
            <span>
              {new Date(data[hoveredIndex].timestamp).toLocaleString('en-US', {
                month: 'short',
                day: 'numeric',
                year: 'numeric',
                hour: 'numeric',
                minute: '2-digit',
              })}
            </span>
          </div>
          <div className="mt-2 space-y-1 font-semibold">
            <div className="text-emerald-600">+{formatAmount(data[hoveredIndex].revenue)}</div>
            <div className="text-rose-600">-{formatAmount(data[hoveredIndex].expenses)}</div>
          </div>
        </div>
      )}
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-56">
        <defs>
          <linearGradient id="analyticsArea" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="#67C382" stopOpacity="0.35" />
            <stop offset="100%" stopColor="#67C382" stopOpacity="0.05" />
          </linearGradient>
        </defs>
        {yLabels.map((label) => (
          <line
            key={`grid-${label.y}`}
            x1={padding}
            x2={width - padding}
            y1={label.y}
            y2={label.y}
            stroke="#E5E7EB"
            strokeDasharray="4 4"
          />
        ))}
        <path d={areaPath} fill="url(#analyticsArea)" stroke="none" />
        <path d={linePath} fill="none" stroke="#5DBE74" strokeWidth="2" />
        {points.map((point, idx) => (
          <circle
            key={`point-${idx}`}
            cx={point.x}
            cy={point.y}
            r="3.5"
            fill="#5DBE74"
            onMouseEnter={() => setHoveredIndex(idx)}
            onMouseLeave={() => setHoveredIndex(null)}
          />
        ))}
      </svg>

      <div className="absolute left-0 top-2 bottom-6 flex flex-col justify-between text-xs text-gray-400">
        {yLabels.map((label) => (
          <span key={`label-${label.value}`} className="leading-none">
            {label.value}
          </span>
        ))}
      </div>
    </div>
  );
}

export default function VendorAnalytics() {
  const navigate = useNavigate();
  const [viewMode, setViewMode] = useState<ViewMode>('products');
  const [selectedRange, setSelectedRange] = useState('1Y');
  const [search, setSearch] = useState('');
  const [summary, setSummary] = useState<VendorAnalyticsSummary | null>(null);
  const [stats, setStats] = useState<VendorAnalyticsStats | null>(null);
  const [chartData, setChartData] = useState<VendorAnalyticsChartPoint[]>([]);
  const [rows, setRows] = useState<AnalyticsRow[]>([]);
  const [rowsMeta, setRowsMeta] = useState<VendorEarningsItemsResponse<AnalyticsRow> | null>(null);
  const [loading, setLoading] = useState(false);
  const [chartLoading, setChartLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [endDate, setEndDate] = useState<Date>(() => new Date());
  const [startDate, setStartDate] = useState<Date>(() => getRangeStart(new Date(), '1Y'));
  const { currentCurrency, exchangeRates, fetchExchangeRate, setCurrency } = useCurrencyStore();

  useEffect(() => {
    fetchExchangeRate();
  }, [fetchExchangeRate]);

  const dateParams = useMemo(() => {
    const toParam = (value: Date) => value.toISOString().split('T')[0];
    return {
      start_date: toParam(startDate),
      end_date: toParam(endDate),
    };
  }, [startDate, endDate]);

  const formatAmount = (amount: number) =>
    formatPriceWithConversion(amount, 'NGN', currentCurrency, exchangeRates);

  const rangeLabel = useMemo(() => {
    const format = (value: Date) =>
      value.toLocaleDateString('en-US', { month: 'short', day: '2-digit', year: 'numeric' });
    return `${format(startDate)} - ${format(endDate)}`;
  }, [startDate, endDate]);

  const comparisonLabel = useMemo(() => {
    const days = Math.max(1, Math.round((endDate.getTime() - startDate.getTime()) / 86400000) + 1);
    return `vs Previous ${days} Day${days === 1 ? '' : 's'}`;
  }, [startDate, endDate]);

  const fetchSummary = async () => {
    try {
      const response = await vendorService.getAnalyticsSummary(dateParams);
      setSummary(response);
    } catch (err: any) {
      setError(err?.message || 'Failed to load analytics summary');
    }
  };

  const fetchStats = async () => {
    try {
      const response = await vendorService.getAnalyticsStats(dateParams);
      setStats(response);
    } catch (err: any) {
      setError(err?.message || 'Failed to load analytics stats');
    }
  };

  const fetchChart = async () => {
    try {
      setChartLoading(true);
      const response = await vendorService.getAnalyticsChart({
        range: selectedRange,
        ...dateParams,
      });
      setChartData(response.points || []);
    } catch (err: any) {
      setError(err?.message || 'Failed to load analytics chart');
      setChartData([]);
    } finally {
      setChartLoading(false);
    }
  };

  const fetchRows = async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await vendorService.getEarningsItems({
        view: viewMode,
        page: 1,
        page_size: 20,
        search: search || undefined,
        ...dateParams,
      });
      setRows(response.items || []);
      setRowsMeta(response as VendorEarningsItemsResponse<AnalyticsRow>);
    } catch (err: any) {
      setError(err?.message || 'Failed to load analytics items');
      setRows([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSummary();
    fetchStats();
    fetchChart();
    fetchRows();
  }, [viewMode, search, dateParams, selectedRange]);

  const handleRangeSelect = (range: string) => {
    const end = new Date();
    const start = getRangeStart(end, range);
    setSelectedRange(range);
    setStartDate(start);
    setEndDate(end);
  };

  const renderChange = (value?: number | null) => {
    if (value === null || value === undefined) {
      return <span className="text-gray-400">--</span>;
    }
    const isPositive = value >= 0;
    const displayValue = `${Math.abs(value).toFixed(1)}%`;
    return (
      <span className={`flex items-center gap-1 text-sm font-semibold ${isPositive ? 'text-emerald-600' : 'text-rose-600'}`}>
        <TrendingUp className={`w-4 h-4 ${isPositive ? '' : 'rotate-180'}`} />
        {displayValue}
      </span>
    );
  };

  const buildItemsListed = (items?: string[]) => {
    if (!items?.length) return '--';
    const [first, ...rest] = items;
    return rest.length ? `${first} +${rest.length}` : first;
  };

  const formatDate = (value?: string | null) => {
    if (!value) return '--';
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return '--';
    return parsed.toLocaleDateString('en-US', { month: '2-digit', day: '2-digit', year: '2-digit' });
  };

  const importantStats = [
    {
      label: 'Total Products Sold',
      value: stats?.total_products_sold?.toLocaleString('en-US') ?? '--',
      icon: ShoppingBag,
    },
    {
      label: 'Wishlisted Products',
      value: stats?.wishlisted_products?.toLocaleString('en-US') ?? '--',
      icon: Heart,
    },
    {
      label: 'Returning Customers',
      value: stats?.returning_customers?.toLocaleString('en-US') ?? '--',
      icon: UserCheck,
    },
    {
      label: 'New Customers',
      value: stats?.new_customers?.toLocaleString('en-US') ?? '--',
      icon: UserPlus,
    },
  ];

  const productsCount = viewMode === 'products' ? rowsMeta?.total : null;
  const ordersCount = viewMode === 'orders' ? rowsMeta?.total : null;

  return (
    <div className="flex min-h-screen bg-[var(--color-page-bg)]">
      <VendorSidebar activePrimary="analytics" />

      <div className="flex-1">
        <div className="px-8 py-8 space-y-8">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <h1 className="text-2xl font-semibold text-gray-900">Analytics</h1>
            <div className="flex items-center gap-3 flex-1 justify-end">
              <CurrencySwitcher className="mr-2" value={currentCurrency} onChange={setCurrency} />
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
                <input
                  type="text"
                  placeholder="Search"
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  className="pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#105E53] focus:border-transparent w-64"
                />
              </div>
              <button
                type="button"
                className="p-2 border border-gray-300 rounded-lg hover:bg-gray-50 transition"
              >
                <Filter className="h-5 w-5 text-gray-600" />
              </button>
              <button
                type="button"
                className="p-2 border border-gray-300 rounded-lg hover:bg-gray-50 transition"
              >
                <Upload className="h-5 w-5 text-gray-600" />
              </button>
            </div>
          </div>

          <div className="flex flex-wrap items-start justify-between gap-6">
            <div className="space-y-4 min-w-[280px]">
              <div className="flex items-center gap-2 text-sm text-gray-500">
                <span>Total Revenue</span>
                <ChevronDown className="w-4 h-4 text-gray-400" />
              </div>
              <div className="flex items-center gap-3 flex-wrap">
                <p className="text-4xl font-semibold text-gray-900 tracking-tight">
                  {formatAmount(summary?.total_revenue ?? 0)}
                </p>
                {renderChange(summary?.revenue_change_pct)}
                <span className="text-sm text-gray-400">{comparisonLabel}</span>
              </div>
              <p className="text-xs text-gray-400">
                The current cut percentage is {summary?.commission_rate_pct?.toFixed(1) ?? '--'}%
              </p>
            </div>

            <div className="flex flex-col items-end gap-3">
              <div className="text-sm text-gray-400">Showing trends for:</div>
              <div className="text-sm font-semibold text-gray-800">{rangeLabel}</div>
              <div className="flex items-center gap-2">
                {['1D', '7D', '1M', '1Y'].map((range) => (
                  <button
                    key={range}
                    type="button"
                    onClick={() => handleRangeSelect(range)}
                    className={`px-3 py-2 rounded-lg text-xs font-semibold border ${
                      selectedRange === range
                        ? 'bg-gray-900 text-white border-gray-900'
                        : 'border-gray-200 text-gray-700 bg-white'
                    }`}
                  >
                    {range}
                  </button>
                ))}
                <button
                  type="button"
                  className="p-2 border border-gray-200 rounded-lg hover:bg-gray-50 transition"
                >
                  <Calendar className="h-4 w-4 text-gray-600" />
                </button>
              </div>
            </div>
          </div>

          <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6">
            {chartLoading ? (
              <div className="h-56 flex items-center justify-center text-sm text-gray-400">
                Loading chart...
              </div>
            ) : (
              <>
                <AnalyticsChart data={chartData} formatAmount={formatAmount} />
                <div
                  className="mt-2 grid text-xs text-gray-400"
                  style={{ gridTemplateColumns: `repeat(${Math.max(chartData.length, 1)}, minmax(0, 1fr))` }}
                >
                  {chartData.map((point, index) => (
                    <span key={`${point.timestamp}-${index}`} className="col-span-1 text-center">
                      {formatAxisLabel(point.timestamp, selectedRange)}
                    </span>
                  ))}
                </div>
              </>
            )}
          </div>

          <div className="space-y-3">
            <p className="text-sm text-gray-500">Important Stats</p>
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
              {importantStats.map((stat) => {
                const Icon = stat.icon;
                return (
                  <div
                    key={stat.label}
                    className="bg-white rounded-2xl border border-gray-200 shadow-sm p-5 flex items-center gap-4"
                  >
                    <div className="h-12 w-12 rounded-2xl bg-gray-100 flex items-center justify-center">
                      <Icon className="w-5 h-5 text-gray-700" />
                    </div>
                    <div>
                      <p className="text-xs text-gray-400">{stat.label}</p>
                      <p className="text-xl font-semibold text-gray-900">{stat.value}</p>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="space-y-4">
            <div className="flex items-center gap-3 text-sm text-gray-500">
              <span>View by:</span>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setViewMode('products')}
                  className={`px-4 py-2 rounded-full text-xs font-semibold border ${
                    viewMode === 'products'
                      ? 'bg-gray-900 text-white border-gray-900'
                      : 'border-gray-200 text-gray-700'
                  }`}
                >
                  Products{productsCount ? ` (${productsCount})` : ''}
                </button>
                <button
                  type="button"
                  onClick={() => setViewMode('orders')}
                  className={`px-4 py-2 rounded-full text-xs font-semibold border ${
                    viewMode === 'orders'
                      ? 'bg-gray-900 text-white border-gray-900'
                      : 'border-gray-200 text-gray-700'
                  }`}
                >
                  Orders{ordersCount ? ` (${ordersCount})` : ''}
                </button>
              </div>
            </div>

            <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 text-gray-500">
                  <tr>
                    <th className="px-4 py-3 text-left font-semibold">Order Number</th>
                    <th className="px-4 py-3 text-left font-semibold">Items Listed</th>
                    <th className="px-4 py-3 text-left font-semibold">Status</th>
                    <th className="px-4 py-3 text-left font-semibold">Quantity</th>
                    <th className="px-4 py-3 text-left font-semibold">Cut Taken</th>
                    <th className="px-4 py-3 text-left font-semibold">Earnings</th>
                    <th className="px-4 py-3 text-left font-semibold">Date</th>
                    <th className="px-4 py-3 text-left font-semibold"></th>
                  </tr>
                </thead>
                <tbody>
                  {loading ? (
                    <tr>
                      <td colSpan={8} className="px-4 py-6 text-center text-gray-500">
                        Loading analytics...
                      </td>
                    </tr>
                  ) : rows.length === 0 ? (
                    <tr>
                      <td colSpan={8} className="px-4 py-6 text-center text-gray-500">
                        No analytics data found for this period.
                      </td>
                    </tr>
                  ) : (
                    rows.map((row) => {
                      const isProductView = viewMode === 'products';
                      const displayStatus = isProductView
                        ? (row as VendorEarningsProductRow).status
                        : (row as VendorEarningsOrderRow).status;
                      const quantity = isProductView
                        ? (row as VendorEarningsProductRow).quantity
                        : (row as VendorEarningsOrderRow).total_quantity;
                      const cutTaken = isProductView
                        ? (row as VendorEarningsProductRow).commission_amount
                        : (row as VendorEarningsOrderRow).total_commission;
                      const earnings = isProductView
                        ? (row as VendorEarningsProductRow).vendor_payout
                        : (row as VendorEarningsOrderRow).total_payout;
                      const orderNumber = isProductView
                        ? (row as VendorEarningsProductRow).order_number
                        : (row as VendorEarningsOrderRow).order_number;
                      const itemsListed = isProductView
                        ? (row as VendorEarningsProductRow).product_title
                        : buildItemsListed((row as VendorEarningsOrderRow).items);
                      const deliveredAt = isProductView
                        ? (row as VendorEarningsProductRow).delivered_at
                        : (row as VendorEarningsOrderRow).delivered_at;
                      return (
                        <tr key={row.id} className="border-t border-gray-100">
                          <td className="px-4 py-3 text-gray-700">{orderNumber}</td>
                          <td className="px-4 py-3 text-gray-700">{itemsListed}</td>
                          <td className="px-4 py-3">
                            <StatusPill status={displayStatus} />
                          </td>
                          <td className="px-4 py-3 text-gray-700">{quantity}</td>
                          <td className="px-4 py-3 text-gray-700">
                            {formatAmount(cutTaken)}
                          </td>
                          <td className="px-4 py-3 text-gray-700">
                            {formatAmount(earnings)}
                          </td>
                          <td className="px-4 py-3 text-gray-700">{formatDate(deliveredAt)}</td>
                          <td className="px-4 py-3">
                            <button
                              type="button"
                              onClick={() => {
                                if (viewMode === 'products') {
                                  const targetId = (row as VendorEarningsProductRow).product_id;
                                  navigate(`${ROUTES.VENDOR_PRODUCTS}/${targetId}/view`);
                                } else {
                                  navigate(`/vendor/orders/${row.id}`);
                                }
                              }}
                              className="w-9 h-9 rounded-full border border-gray-200 flex items-center justify-center hover:bg-gray-50"
                            >
                              <Eye className="w-4 h-4 text-gray-500" />
                            </button>
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {error && (
            <div className="text-sm text-rose-500">{error}</div>
          )}
        </div>
      </div>
    </div>
  );
}
