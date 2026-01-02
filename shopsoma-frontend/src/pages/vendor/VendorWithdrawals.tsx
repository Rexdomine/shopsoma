import {
  ArrowLeft,
  Calendar,
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
import { vendorService, type VendorPayout } from '../../services/vendorService';
import { useToast } from '../../hooks/useToast';
import ToastContainer from '../../components/ui/ToastContainer';

const getRangeStart = (end: Date, range: string) => {
  const start = new Date(end);
  if (range === '1D') {
    start.setDate(end.getDate() - 1);
  } else if (range === '7D') {
    start.setDate(end.getDate() - 7);
  } else if (range === '1M') {
    start.setMonth(end.getMonth() - 1);
  } else if (range === '6M') {
    start.setMonth(end.getMonth() - 6);
  }
  return start;
};

function StatusBadge({ status }: { status: string }) {
  const normalized = status.toLowerCase();
  if (normalized === 'completed') {
    return <span className="px-3 py-1 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700">Delivered</span>;
  }
  if (normalized === 'failed') {
    return <span className="px-3 py-1 rounded-full text-xs font-semibold bg-rose-50 text-rose-700">Cancelled</span>;
  }
  return <span className="px-3 py-1 rounded-full text-xs font-semibold bg-amber-50 text-amber-700">Pending</span>;
}

export default function VendorWithdrawals() {
  const navigate = useNavigate();
  const { toasts, hideToast, success, error: showError } = useToast();
  const [showWithdraw, setShowWithdraw] = useState(false);
  const [payouts, setPayouts] = useState<VendorPayout[]>([]);
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [detailPayout, setDetailPayout] = useState<VendorPayout | null>(null);
  const [canceling, setCanceling] = useState(false);
  const [search, setSearch] = useState('');
  const [endDate, setEndDate] = useState<Date>(() => new Date());
  const [selectedRange, setSelectedRange] = useState('6M');
  const [startDate, setStartDate] = useState<Date>(() => getRangeStart(new Date(), '6M'));
  const { currentCurrency, exchangeRates, fetchExchangeRate, setCurrency } = useCurrencyStore();

  useEffect(() => {
    fetchExchangeRate();
  }, [fetchExchangeRate]);

  const formatAmount = (amount: number) =>
    formatPriceWithConversion(amount, 'NGN', currentCurrency, exchangeRates);

  const formatDate = (value?: string | null) => {
    if (!value) return '—';
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return '—';
    return parsed.toLocaleDateString('en-US', { month: '2-digit', day: '2-digit', year: '2-digit' });
  };

  const formattedDateRange = useMemo(() => {
    const format = (value: Date) =>
      value.toLocaleDateString('en-US', { month: 'short', day: '2-digit', year: 'numeric' });
    return `${format(startDate)} - ${format(endDate)}`;
  }, [startDate, endDate]);

  const dateParams = useMemo(() => {
    const toParam = (value: Date) => value.toISOString().split('T')[0];
    return {
      start_date: toParam(startDate),
      end_date: toParam(endDate),
    };
  }, [startDate, endDate]);

  const handleRangeSelect = (range: string) => {
    const end = new Date();
    const start = getRangeStart(end, range);
    setSelectedRange(range);
    setStartDate(start);
    setEndDate(end);
    setCurrentPage(1);
  };

  const fetchPayouts = async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await vendorService.listPayouts({
        page: currentPage,
        page_size: 20,
        search: search || undefined,
        ...dateParams,
      });
      setPayouts(response.payouts || []);
      setTotalPages(response.total_pages || 1);
    } catch (err: any) {
      setError(err?.message || 'Failed to load withdrawals.');
      setPayouts([]);
      setTotalPages(1);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPayouts();
  }, [currentPage, search, dateParams]);

  useEffect(() => {
    const handler = setTimeout(() => {
      if (search) {
        setCurrentPage(1);
      }
    }, 300);
    return () => clearTimeout(handler);
  }, [search]);

  const currentWithdrawal = useMemo(() => {
    return payouts.find((payout) => payout.status !== 'completed' && payout.status !== 'failed') || null;
  }, [payouts]);

  const getDestination = (payout: VendorPayout) => {
    if (!payout.notes) return 'Payout account';
    return payout.notes.replace('Vendor requested payout via ', '');
  };

  const openDetail = async (payout: VendorPayout) => {
    setDetailOpen(true);
    setDetailPayout(payout);
    setDetailLoading(true);
    setDetailError(null);
    try {
      const full = await vendorService.getPayout(payout.id);
      setDetailPayout(full);
    } catch (err: any) {
      setDetailError(err?.message || 'Failed to load payout details.');
    } finally {
      setDetailLoading(false);
    }
  };

  const handleCancelWithdrawal = async () => {
    if (!currentWithdrawal) {
      return;
    }
    const confirmed = window.confirm('Cancel this withdrawal request?');
    if (!confirmed) {
      return;
    }
    try {
      setCanceling(true);
      await vendorService.cancelPayout(currentWithdrawal.id);
      success('Withdrawal cancelled successfully');
      await fetchPayouts();
    } catch (err: any) {
      showError(err?.message || 'Failed to cancel withdrawal');
    } finally {
      setCanceling(false);
    }
  };

  return (
    <>
      <div className="flex min-h-screen bg-[var(--color-page-bg)]">
      <VendorSidebar activePrimary="earnings" />

      <div className="flex-1">
        <div className="px-8 py-8 space-y-8">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-center gap-2 text-sm text-gray-600">
              <button
                type="button"
                onClick={() => navigate(ROUTES.VENDOR_EARNINGS)}
                className="flex items-center gap-2 text-gray-600 hover:text-gray-900"
              >
                <ArrowLeft className="w-4 h-4" />
                Back to Earnings Graph
              </button>
            </div>
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

          <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-5 flex flex-wrap items-start gap-6">
            <div className="flex-1 space-y-3 min-w-[280px]">
              <div className="flex items-center gap-2 text-sm text-emerald-600">
                <span className="h-6 w-6 rounded-full border border-emerald-200 bg-emerald-50 flex items-center justify-center text-emerald-600">
                  ●
                </span>
                <span>Current Withdrawal</span>
              </div>
              <div className="flex items-center gap-3 flex-wrap">
                <p className="text-4xl font-semibold text-gray-900 tracking-tight">
                  {formatAmount(currentWithdrawal?.payout_amount || 0)}
                </p>
                <span className="text-sm font-semibold text-emerald-600 flex items-center gap-1">
                  <TrendingUp className="w-4 h-4" />
                  16%
                </span>
              </div>
              <div className="flex items-center gap-4 text-sm text-gray-600">
                <span>Initiated: {formatDate(currentWithdrawal?.created_at)}</span>
                <span>Expected: {formatDate(currentWithdrawal?.processed_at)}</span>
              </div>

              <div>
                <p className="text-sm text-gray-500 mb-1">Destination Account</p>
                <div className="w-full max-w-md px-4 py-3 rounded-lg border border-gray-200 bg-gray-50 text-gray-700">
                  {currentWithdrawal ? getDestination(currentWithdrawal) : '—'}
                </div>
              </div>
            </div>

            <div className="flex flex-col items-end gap-3 min-w-[200px]">
              <button
                type="button"
                onClick={handleCancelWithdrawal}
                disabled={!currentWithdrawal || canceling}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-full border border-rose-100 bg-rose-50 text-rose-700 text-sm font-semibold hover:bg-rose-100 transition"
              >
                <Upload className="w-4 h-4" />
                {canceling ? 'Cancelling...' : 'Cancel Withdrawal'}
              </button>
            </div>
          </div>

          <div className="space-y-2">
            <div className="flex items-center gap-2 text-gray-700 text-sm">
              <Upload className="w-4 h-4 text-gray-500" />
              <span>Withdrawal History</span>
            </div>

            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="space-y-1 text-sm">
                <p className="text-gray-400">Showing info for:</p>
                <p className="text-gray-800 font-semibold">{formattedDateRange}</p>
              </div>

              <div className="flex items-center gap-2">
                {['1D', '7D', '1M', '6M'].map((range) => (
                  <button
                    key={range}
                    type="button"
                    className={`px-4 py-2 rounded-lg text-xs font-semibold border ${
                      range === selectedRange ? 'bg-gray-900 text-white border-gray-900' : 'border-gray-200 text-gray-700 bg-white'
                    }`}
                    onClick={() => handleRangeSelect(range)}
                  >
                    {range}
                  </button>
                ))}
                <button
                  type="button"
                  className="h-10 w-10 rounded-lg border border-gray-200 flex items-center justify-center bg-white"
                >
                  <Calendar className="w-4 h-4 text-gray-600" />
                </button>
              </div>
            </div>
          </div>

          <div className="bg-white border border-gray-200 rounded-2xl shadow-sm overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500">S/N</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500">Amount Withdrawn</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500">Initiated</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500">Withdrawn</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500">Destination Account</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500">Status</th>
                  <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500"> </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {loading && (
                  <tr>
                    <td className="px-4 py-6 text-center text-gray-500" colSpan={7}>
                      Loading withdrawals...
                    </td>
                  </tr>
                )}
                {!loading && error && (
                  <tr>
                    <td className="px-4 py-6 text-center text-red-600" colSpan={7}>
                      {error}
                    </td>
                  </tr>
                )}
                {!loading && !error && payouts.length === 0 && (
                  <tr>
                    <td className="px-4 py-6 text-center text-gray-500" colSpan={7}>
                      No withdrawals found for this period.
                    </td>
                  </tr>
                )}
                {!loading && !error && payouts.map((row, idx) => (
                  <tr key={row.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3 text-gray-800">{String(idx + 1).padStart(2, '0')}.</td>
                    <td className="px-4 py-3 font-semibold text-gray-900">{formatAmount(row.payout_amount)}</td>
                    <td className="px-4 py-3 text-gray-800">{formatDate(row.created_at)}</td>
                    <td className="px-4 py-3 text-gray-800">{formatDate(row.processed_at)}</td>
                    <td className="px-4 py-3 text-gray-800">{getDestination(row)}</td>
                    <td className="px-4 py-3">
                      <StatusBadge status={row.status} />
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        type="button"
                        className="h-8 w-8 rounded-full border border-gray-200 flex items-center justify-center hover:bg-gray-100"
                        aria-label="View details"
                        onClick={() => openDetail(row)}
                      >
                        <Eye className="w-4 h-4 text-gray-600" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="flex items-center justify-between text-sm text-gray-600">
            <button
              type="button"
              className="px-3 py-1 border border-gray-200 rounded-lg disabled:opacity-50"
              onClick={() => setCurrentPage((prev) => Math.max(1, prev - 1))}
              disabled={currentPage <= 1}
            >
              Prev
            </button>
            <span>Page {currentPage} of {totalPages}</span>
            <button
              type="button"
              className="px-3 py-1 border border-gray-200 rounded-lg disabled:opacity-50"
              onClick={() => setCurrentPage((prev) => Math.min(totalPages, prev + 1))}
              disabled={currentPage >= totalPages}
            >
              Next
            </button>
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
      {detailOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-md p-6 relative">
            <button
              type="button"
              onClick={() => setDetailOpen(false)}
              className="absolute right-4 top-4 text-gray-400 hover:text-gray-600"
              aria-label="Close"
            >
              ×
            </button>
            <h3 className="text-lg font-semibold text-gray-900 mb-4">Withdrawal Details</h3>
            {detailLoading && (
              <p className="text-sm text-gray-500">Loading payout details...</p>
            )}
            {detailError && (
              <p className="text-sm text-red-600">{detailError}</p>
            )}
            {!detailLoading && detailPayout && (
              <div className="space-y-3 text-sm text-gray-700">
                <div className="flex items-center justify-between">
                  <span className="text-gray-500">Amount</span>
                  <span className="font-semibold text-gray-900">{formatAmount(detailPayout.payout_amount)}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-gray-500">Status</span>
                  <span className="font-semibold text-gray-900 capitalize">{detailPayout.status}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-gray-500">Period</span>
                  <span className="text-gray-900">
                    {formatDate(detailPayout.payout_period_start)} - {formatDate(detailPayout.payout_period_end)}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-gray-500">Requested</span>
                  <span className="text-gray-900">{formatDate(detailPayout.created_at)}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-gray-500">Processed</span>
                  <span className="text-gray-900">{formatDate(detailPayout.processed_at)}</span>
                </div>
                <div className="space-y-1">
                  <p className="text-gray-500">Destination</p>
                  <p className="text-gray-900">{getDestination(detailPayout)}</p>
                </div>
                <div className="space-y-1">
                  <p className="text-gray-500">Reference</p>
                  <p className="text-gray-900">{detailPayout.payment_reference || '—'}</p>
                </div>
                <div className="space-y-1">
                  <p className="text-gray-500">Notes</p>
                  <p className="text-gray-900">{detailPayout.notes || '—'}</p>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
      <ToastContainer toasts={toasts} onClose={hideToast} />
    </>
  );
}
