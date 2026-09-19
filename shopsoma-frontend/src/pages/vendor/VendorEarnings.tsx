import {
  Calendar,
  ChevronDown,
  Eye,
  Filter,
  Search,
  TrendingUp,
  Upload,
} from 'lucide-react';
import VendorSidebar from '../../components/vendor/VendorSidebar';
import { useNavigate } from 'react-router-dom';
import { ROUTES } from '../../config/constants';
import { useEffect, useMemo, useState } from 'react';
import WithdrawModal from '../../components/vendor/WithdrawModal';
import CurrencySwitcher from '../../components/common/CurrencySwitcher';
import { useCurrencyStore } from '../../store/currencyStore';
import { formatPriceWithConversion } from '../../utils/pricing';
import { useToast } from '../../hooks/useToast';
import ToastContainer from '../../components/ui/ToastContainer';
import {
  vendorService,
  type VendorEarningsProductRow,
  type VendorEarningsOrderRow,
  type VendorEarningsSummary,
  type EarningsViewMode,
  type VendorPayoutStatus,
} from '../../services/vendorService';

type EarningsRow = VendorEarningsProductRow | VendorEarningsOrderRow;

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

function StatusPill({ status }: { status: string }) {
  if (status.toLowerCase() === 'delivered') {
    return <span className="px-4 py-1 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700">Complete</span>;
  }
  return <span className="px-4 py-1 rounded-full text-xs font-semibold bg-amber-50 text-amber-700">Pending</span>;
}

export default function VendorEarnings() {
  const navigate = useNavigate();
  const { toasts, hideToast, success, error: showError } = useToast();
  const [showWithdraw, setShowWithdraw] = useState(false);
  const [viewMode, setViewMode] = useState<EarningsViewMode>('products');
  const [summary, setSummary] = useState<VendorEarningsSummary | null>(null);
  const [rows, setRows] = useState<EarningsRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [endDate, setEndDate] = useState<Date>(() => new Date());
  const [selectedRange, setSelectedRange] = useState('1Y');
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

  const formattedDateRange = useMemo(() => {
    const format = (value: Date) =>
      value.toLocaleDateString('en-US', { month: 'short', day: '2-digit', year: 'numeric' });
    return `${format(startDate)} - ${format(endDate)}`;
  }, [startDate, endDate]);
  const comparisonLabel = useMemo(() => {
    const days = Math.max(1, Math.round((endDate.getTime() - startDate.getTime()) / 86400000) + 1);
    return `vs Previous ${days} Day${days === 1 ? '' : 's'}`;
  }, [startDate, endDate]);

  const formatAmount = (amount: number) =>
    formatPriceWithConversion(amount, 'NGN', currentCurrency, exchangeRates);

  const fetchSummary = async () => {
    try {
      const response = await vendorService.getEarningsSummary(dateParams);
      setSummary(response);
    } catch (err: any) {
      setError(err?.message || 'Failed to load earnings summary');
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
    } catch (err: any) {
      setError(err?.message || 'Failed to load earnings items');
      setRows([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSummary();
    fetchRows();
  }, [viewMode, search, dateParams]);

  const handleRangeSelect = (range: string) => {
    const end = new Date();
    const start = range === '6M' ? (() => {
      const sixMonthStart = new Date(end);
      sixMonthStart.setMonth(end.getMonth() - 6);
      return sixMonthStart;
    })() : getRangeStart(end, range);
    setSelectedRange(range);
    setStartDate(start);
    setEndDate(end);
  };

  const buildItemsListed = (items?: string[]) => {
    if (!items?.length) return '—';
    const [first, ...rest] = items;
    return rest.length ? `${first} +${rest.length}` : first;
  };

  const formatDate = (value?: string | null) => {
    if (!value) return '—';
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return '—';
    return parsed.toLocaleDateString('en-US', { month: '2-digit', day: '2-digit', year: '2-digit' });
  };
  const renderWithdrawalBadge = (available?: boolean, daysLeft?: number | null) => {
    if (typeof daysLeft === 'number' && daysLeft > 0) {
      return (
        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-gray-100 text-gray-600">
          {daysLeft} days left
        </span>
      );
    }
    if (available || daysLeft === 0) {
      return (
        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-50 text-emerald-700">
          Available
        </span>
      );
    }
    return null;
  };
  const renderPayoutStatusBadge = (
    payoutStatus?: VendorPayoutStatus | null,
    available?: boolean,
    daysLeft?: number | null,
  ) => {
    const normalized = payoutStatus || 'available';
    if (normalized === 'completed' || normalized === 'paid_out') {
      return (
        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-50 text-emerald-700">
          Paid out
        </span>
      );
    }
    if (normalized === 'pending') {
      return (
        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-amber-50 text-amber-700">
          Withdrawal pending
        </span>
      );
    }
    if (normalized === 'processing') {
      return (
        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-blue-50 text-blue-700">
          Processing
        </span>
      );
    }
    if (normalized === 'failed') {
      return (
        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-rose-50 text-rose-700">
          Withdrawal failed
        </span>
      );
    }
    return renderWithdrawalBadge(available, daysLeft);
  };
  const tableColumns = viewMode === 'products' ? 9 : 8;
  const renderChange = (value?: number | null) => {
    if (value === null || value === undefined) {
      return <span className="text-gray-400">—</span>;
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
  const earningsDetailState = {
    returnTo: ROUTES.VENDOR_EARNINGS,
    returnLabel: 'Back to Earnings & Payouts',
    activePrimary: 'earnings',
  };

  return (
    <>
      <div className="flex min-h-screen bg-[var(--color-page-bg)]">
      <VendorSidebar activePrimary="earnings" />

      <div className="flex-1">
        <div className="px-8 py-8 space-y-8">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <h1 className="text-2xl font-semibold text-gray-900">Earnings & Payout</h1>
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

          <div className="w-full flex items-start justify-between gap-8">
            <div className="flex-1 space-y-6">
              <div className="space-y-3">
                <p className="text-sm text-gray-400">Current Earnings</p>
                <div className="flex items-center gap-4">
                  <p className="text-4xl font-semibold text-gray-900 tracking-tight">
                    {formatAmount(summary?.current_earnings ?? 0)}
                  </p>
                  <div className="flex items-center gap-2 text-sm">
                    {renderChange(summary?.current_earnings_change_pct)}
                    <span className="text-gray-500">{comparisonLabel}</span>
                    <ChevronDown className="w-4 h-4 text-gray-400" />
                  </div>
                </div>
              </div>

              <div className="space-y-2">
                <div className="flex items-start gap-8">
                  <div className="space-y-1">
                    <p className="text-sm text-gray-400">Projected Earnings</p>
                  <div className="flex items-center gap-2">
                    <p className="text-2xl font-semibold text-gray-900 tracking-tight">
                      {formatAmount(summary?.projected_earnings ?? 0)}
                    </p>
                    <span className="text-xs">{renderChange(summary?.projected_earnings_change_pct)}</span>
                  </div>
                </div>

                  <div className="space-y-2">
                    <p className="text-sm text-gray-400 flex items-center gap-2">
                      <span className="h-5 w-5 rounded-full border border-gray-300 text-gray-500 flex items-center justify-center text-xs">i</span>
                      Expenses
                    </p>
                    <div className="flex items-center gap-2">
                      <p className="text-2xl font-semibold text-gray-900 tracking-tight">
                        {formatAmount(summary?.expenses ?? 0)}
                      </p>
                      <span className="text-xs">{renderChange(summary?.expenses_change_pct)}</span>
                    </div>
                    <button
                      type="button"
                      className="text-sm text-gray-500 underline"
                      onClick={() => navigate(`${ROUTES.VENDOR_EXPENSES}?view=orders`)}
                    >
                      View All
                    </button>
                  </div>
                </div>
              </div>
            </div>

            <div className="flex flex-col items-end gap-3 w-full max-w-xs">
              <div className="space-y-1 text-right">
                <p className="text-sm text-gray-400">Showing info for:</p>
                <p className="text-sm font-semibold text-gray-800">{formattedDateRange}</p>
              </div>

              <div className="flex items-center gap-2">
                {['1D', '7D', '1M', '6M'].map((range) => (
                  <button
                    key={range}
                    type="button"
                    className={`px-4 py-2 rounded-lg text-xs font-semibold border ${
                      selectedRange === range ? 'border-gray-900 bg-gray-900 text-white' : 'border-gray-200 bg-white text-gray-700'
                    }`}
                    onClick={() => handleRangeSelect(range)}
                  >
                    {range}
                  </button>
                ))}
                <button
                  type="button"
                  className="h-10 w-10 rounded-lg border border-gray-900 bg-gray-900 flex items-center justify-center text-white"
                >
                  <Calendar className="w-4 h-4" />
                </button>
              </div>

              <button
                type="button"
                className="inline-flex items-center justify-center gap-2 px-4 py-2 rounded-full border border-gray-200 bg-white shadow-sm text-sm font-semibold text-gray-800"
                onClick={() => navigate(ROUTES.VENDOR_WITHDRAWALS)}
              >
                <Eye className="w-4 h-4 text-gray-600" />
                View Withdrawals
              </button>
            </div>
          </div>

          <div className="flex items-center gap-4 text-sm text-gray-700">
            <span className="text-gray-500">View by:</span>
            <div className="flex items-center gap-2">
              <button
                type="button"
                className={`px-3 py-1.5 rounded-full text-sm font-semibold ${
                  viewMode === 'products' ? 'bg-gray-100 text-gray-800' : 'text-gray-600 hover:bg-gray-100'
                }`}
                onClick={() => setViewMode('products')}
              >
                Products
              </button>
              <button
                type="button"
                className={`px-3 py-1.5 rounded-full text-sm font-semibold ${
                  viewMode === 'orders' ? 'bg-gray-100 text-gray-800' : 'text-gray-600 hover:bg-gray-100'
                }`}
                onClick={() => setViewMode('orders')}
              >
                Orders
              </button>
            </div>
          </div>

          <div className="bg-white border border-gray-200 rounded-2xl shadow-sm overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-gray-50">
                <tr>
                  {viewMode === 'products' && (
                    <>
                      <th className="w-16 px-4 py-3 text-left text-xs font-semibold text-gray-500"> </th>
                      <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500">Product Name</th>
                      <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500">Status</th>
                      <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500">Price</th>
                      <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500">Quantity</th>
                      <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500">Expense</th>
                      <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500">Earnings</th>
                      <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500">Date</th>
                      <th className="w-12 px-4 py-3 text-right text-xs font-semibold text-gray-500"> </th>
                    </>
                  )}
                  {viewMode === 'orders' && (
                    <>
                      <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500">Order Number</th>
                      <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500">Items Listed</th>
                      <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500">Status</th>
                      <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500">Quantity</th>
                      <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500">Cut Taken</th>
                      <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500">Earnings</th>
                      <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500">Date</th>
                      <th className="w-12 px-4 py-3 text-right text-xs font-semibold text-gray-500"> </th>
                    </>
                  )}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {loading && (
                  <tr>
                    <td className="px-4 py-6 text-center text-gray-500" colSpan={tableColumns}>
                      Loading earnings...
                    </td>
                  </tr>
                )}
                {!loading && error && (
                  <tr>
                    <td className="px-4 py-6 text-center text-red-600" colSpan={tableColumns}>
                      {error}
                    </td>
                  </tr>
                )}
                {!loading && !error && rows.length === 0 && (
                  <tr>
                    <td className="px-4 py-6 text-center text-gray-500" colSpan={tableColumns}>
                      No earnings found for this period.
                    </td>
                  </tr>
                )}
                {!loading && !error && rows.length > 0 && viewMode === 'products' && rows.map((row) => {
                  const productRow = row as VendorEarningsProductRow;
                  return (
                    <tr key={productRow.id} className="hover:bg-gray-50">
                      <td className="px-4 py-3">
                        {productRow.product_image_url ? (
                          <img
                            src={productRow.product_image_url}
                            alt={productRow.product_title}
                            className="h-12 w-10 rounded-full border border-gray-200 object-cover"
                          />
                        ) : (
                          <div className="h-12 w-10 rounded-full bg-gray-100 border border-gray-200"></div>
                        )}
                      </td>
                      <td className="px-4 py-3 text-gray-900">{productRow.product_title}</td>
                      <td className="px-4 py-3">
                        <StatusPill status={productRow.status} />
                      </td>
                      <td className="px-4 py-3 font-semibold text-gray-900">{formatAmount(productRow.unit_price)}</td>
                      <td className="px-4 py-3 text-gray-800">{productRow.quantity}</td>
                      <td className="px-4 py-3 font-semibold text-gray-900">{formatAmount(productRow.commission_amount)}</td>
                      <td className="px-4 py-3 font-semibold text-gray-900">
                        <div className="flex flex-col gap-1">
                          <span>{formatAmount(productRow.vendor_payout)}</span>
                          {renderPayoutStatusBadge(
                            productRow.payout_status,
                            productRow.withdraw_available,
                            productRow.withdraw_days_left,
                          )}
                        </div>
                      </td>
                      <td className="px-4 py-3 text-gray-700">{formatDate(productRow.delivered_at)}</td>
                      <td className="px-4 py-3 text-right">
                        <button
                          type="button"
                          className="h-8 w-8 rounded-full border border-gray-200 flex items-center justify-center hover:bg-gray-100"
                          aria-label="View details"
                          onClick={() => navigate(`${ROUTES.VENDOR_PRODUCTS}/${productRow.product_id}/view`, { state: earningsDetailState })}
                        >
                          <Eye className="w-4 h-4 text-gray-600" />
                        </button>
                      </td>
                    </tr>
                  );
                })}
                {!loading && !error && rows.length > 0 && viewMode === 'orders' && rows.map((row) => {
                  const orderRow = row as VendorEarningsOrderRow;
                  return (
                    <tr key={orderRow.id} className="hover:bg-gray-50">
                      <td className="px-4 py-3 text-gray-900">{orderRow.order_number}</td>
                      <td className="px-4 py-3 text-gray-700">{buildItemsListed(orderRow.items || [])}</td>
                      <td className="px-4 py-3">
                        <StatusPill status={orderRow.status} />
                      </td>
                      <td className="px-4 py-3 text-gray-800">{orderRow.total_quantity}</td>
                      <td className="px-4 py-3 font-semibold text-gray-900">{formatAmount(orderRow.total_commission)}</td>
                      <td className="px-4 py-3 font-semibold text-gray-900">
                        <div className="flex flex-col gap-1">
                          <span>{formatAmount(orderRow.total_payout)}</span>
                          {renderPayoutStatusBadge(
                            orderRow.payout_status,
                            orderRow.withdraw_available,
                            orderRow.withdraw_days_left,
                          )}
                        </div>
                      </td>
                      <td className="px-4 py-3 text-gray-700">{formatDate(orderRow.delivered_at)}</td>
                      <td className="px-4 py-3 text-right">
                        <button
                          type="button"
                          className="h-8 w-8 rounded-full border border-gray-200 flex items-center justify-center hover:bg-gray-100"
                          aria-label="View details"
                          onClick={() => navigate(ROUTES.VENDOR_ORDER_DETAIL.replace(':id', orderRow.id), { state: earningsDetailState })}
                        >
                          <Eye className="w-4 h-4 text-gray-600" />
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div className="fixed bottom-6 left-0 right-0 flex justify-center md:justify-end md:pr-[22%] md:-translate-x-[50px] pointer-events-none">
        <button
          type="button"
          className="pointer-events-auto inline-flex items-center gap-2 px-6 py-3 rounded-full bg-[#105E53] text-white font-semibold shadow-lg hover:bg-[#0c4c45] transition whitespace-nowrap"
          onClick={() => setShowWithdraw(true)}
        >
          <Upload className="w-4 h-4" />
          Withdraw Funds
        </button>
      </div>
      <WithdrawModal
        open={showWithdraw}
        onClose={() => setShowWithdraw(false)}
        onSuccess={(message) => success(message, 'Success')}
        onError={(message) => showError(message, 'Error')}
      />
      </div>
      <ToastContainer toasts={toasts} onClose={hideToast} />
    </>
  );
}
