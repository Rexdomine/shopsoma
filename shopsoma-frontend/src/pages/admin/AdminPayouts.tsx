import { useCallback, useEffect, useMemo, useState } from 'react';
import { Calendar, Eye, Filter, Search } from 'lucide-react';
import AdminSidebar from '../../components/admin/AdminSidebar';
import CurrencySwitcher from '../../components/common/CurrencySwitcher';
import { useCurrency } from '../../hooks/useCurrency';
import { useToast } from '../../hooks/useToast';
import {
  adminPayoutService,
  downloadCSV,
  type AdminPayout,
  type AdminPayoutAccountDetails,
  type AdminPayoutStatus,
  type AdminPayoutStatusUpdate,
} from '../../services/adminPayoutService';

type StatusFilter = AdminPayoutStatus | 'all';

const STATUS_LABELS: Record<AdminPayoutStatus, string> = {
  pending: 'Pending',
  processing: 'Processing',
  completed: 'Completed',
  failed: 'Failed',
};

const STATUS_BADGES: Record<AdminPayoutStatus, string> = {
  pending: 'bg-amber-50 text-amber-700',
  processing: 'bg-blue-50 text-blue-700',
  completed: 'bg-emerald-50 text-emerald-700',
  failed: 'bg-rose-50 text-rose-700',
};

export default function AdminPayouts() {
  const { toasts, hideToast, success, error, warning } = useToast();
  const { currentCurrency, setCurrency, formatBasePrice } = useCurrency();

  const [payouts, setPayouts] = useState<AdminPayout[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [search, setSearch] = useState('');
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [bulkStatus, setBulkStatus] = useState<AdminPayoutStatus>('processing');
  const [bulkNotes, setBulkNotes] = useState('');
  const [exporting, setExporting] = useState(false);
  const [detailsPayoutId, setDetailsPayoutId] = useState<string | null>(null);
  const [accountDetails, setAccountDetails] = useState<AdminPayoutAccountDetails | null>(null);
  const [accountLoading, setAccountLoading] = useState(false);
  const [accountError, setAccountError] = useState<string | null>(null);

  const today = useMemo(() => new Date(), []);
  const [startDate, setStartDate] = useState<Date>(new Date(today.getFullYear(), 0, 1));
  const [endDate, setEndDate] = useState<Date>(today);
  const [selectedRange, setSelectedRange] = useState('6M');

  const [rowEdits, setRowEdits] = useState<Record<string, AdminPayoutStatusUpdate>>({});
  const [saving, setSaving] = useState<Record<string, boolean>>({});

  const formatAmount = (amount: number | string | null | undefined) =>
    formatBasePrice(Number(amount || 0));

  const formatDate = (value?: string | null) => {
    if (!value) return '—';
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return '—';
    return parsed.toLocaleDateString('en-US', { month: 'short', day: '2-digit', year: 'numeric' });
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
    setSelectedRange(range);
    setStartDate(start);
    setEndDate(end);
    setPage(1);
  };

  const loadPayouts = useCallback(async () => {
    try {
      setLoading(true);
      const response = await adminPayoutService.listPayouts({
        page,
        page_size: pageSize,
        status: statusFilter === 'all' ? undefined : statusFilter,
        search: search || undefined,
        ...dateParams,
      });
      setPayouts(response.payouts);
      setTotal(response.total);
      setTotalPages(response.total_pages || 1);
    } catch (err) {
      console.error('Failed to load payouts:', err);
      error('Failed to load payouts');
      setPayouts([]);
      setTotal(0);
      setTotalPages(1);
    } finally {
      setLoading(false);
    }
  }, [dateParams, error, page, pageSize, search, statusFilter]);

  useEffect(() => {
    loadPayouts();
  }, [loadPayouts]);

  useEffect(() => {
    setRowEdits((prev) => {
      const next = { ...prev };
      payouts.forEach((payout) => {
        next[payout.id] = {
          status: payout.status,
          payment_reference: payout.payment_reference || '',
          notes: payout.notes || '',
        };
      });
      return next;
    });
  }, [payouts]);

  useEffect(() => {
    setSelectedIds([]);
  }, [payouts]);

  const handleUpdate = async (payoutId: string) => {
    const payload = rowEdits[payoutId];
    if (!payload) return;
    try {
      setSaving((prev) => ({ ...prev, [payoutId]: true }));
      await adminPayoutService.updatePayoutStatus(payoutId, payload);
      success('Payout updated');
    } catch (err) {
      console.error('Failed to update payout:', err);
      error('Failed to update payout');
      return;
    } finally {
      setSaving((prev) => ({ ...prev, [payoutId]: false }));
    }
    try {
      await loadPayouts();
    } catch (err) {
      console.error('Failed to refresh payouts:', err);
      warning('Updated payout, but failed to refresh list');
    }
  };

  const handleEditChange = (
    payoutId: string,
    changes: Partial<AdminPayoutStatusUpdate>
  ) => {
    setRowEdits((prev) => ({
      ...prev,
      [payoutId]: {
        ...prev[payoutId],
        ...changes,
      },
    }));
  };

  const handleSelectAll = () => {
    if (selectedIds.length === payouts.length) {
      setSelectedIds([]);
    } else {
      setSelectedIds(payouts.map((payout) => payout.id));
    }
  };

  const handleSelectOne = (payoutId: string) => {
    setSelectedIds((prev) => (
      prev.includes(payoutId)
        ? prev.filter((id) => id !== payoutId)
        : [...prev, payoutId]
    ));
  };

  const handleBulkUpdate = async () => {
    if (!selectedIds.length) {
      error('Select at least one payout');
      return;
    }

    try {
      await adminPayoutService.bulkUpdateStatus({
        payout_ids: selectedIds,
        status: bulkStatus,
        notes: bulkNotes || undefined,
      });
      success('Payouts updated');
      setBulkNotes('');
      setSelectedIds([]);
    } catch (err) {
      console.error('Failed to bulk update payouts:', err);
      error('Failed to update payouts');
      return;
    }
    try {
      await loadPayouts();
    } catch (err) {
      console.error('Failed to refresh payouts:', err);
      warning('Updated payouts, but failed to refresh list');
    }
  };

  const handleExport = async () => {
    try {
      setExporting(true);
      const blob = await adminPayoutService.exportPayoutsCSV({
        status: statusFilter === 'all' ? undefined : statusFilter,
        search: search || undefined,
        ...dateParams,
      });
      downloadCSV(blob, `payouts_${new Date().toISOString().split('T')[0]}.csv`);
      success('Payouts exported');
    } catch (err) {
      console.error('Failed to export payouts:', err);
      error('Failed to export payouts');
    } finally {
      setExporting(false);
    }
  };

  const selectedPayout = useMemo(
    () => payouts.find((payout) => payout.id === detailsPayoutId) || null,
    [detailsPayoutId, payouts]
  );

  const openAccountDetails = async (payoutId: string) => {
    setDetailsPayoutId(payoutId);
    setAccountDetails(null);
    setAccountError(null);
    try {
      setAccountLoading(true);
      const details = await adminPayoutService.getPayoutAccountDetails(payoutId);
      setAccountDetails(details);
    } catch (err) {
      console.error('Failed to load payout account details:', err);
      setAccountError('Failed to load payout account details.');
      error('Failed to load payout account details');
    } finally {
      setAccountLoading(false);
    }
  };

  const closeAccountDetails = () => {
    setDetailsPayoutId(null);
    setAccountDetails(null);
    setAccountError(null);
    setAccountLoading(false);
  };

  return (
    <div className="min-h-screen bg-[var(--color-page-bg)] flex">
      <AdminSidebar activeSection="payouts" />

      <main className="flex-1 p-8 space-y-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold text-gray-900">Payout Management</h1>
            <p className="mt-1 text-sm text-gray-500">
              Review vendor withdrawal requests and payout history
            </p>
          </div>
          <div className="flex items-center gap-3">
            <CurrencySwitcher value={currentCurrency} onChange={setCurrency} />
            <button
              type="button"
              onClick={handleExport}
              disabled={exporting || loading}
              className="px-4 py-2 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50 transition-colors text-sm"
            >
              {exporting ? 'Exporting...' : 'Export CSV'}
            </button>
          </div>
        </div>

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

        <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-5 space-y-5">
          <div className="flex flex-wrap items-center justify-between gap-4">
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
                    range === selectedRange
                      ? 'bg-gray-900 text-white border-gray-900'
                      : 'border-gray-200 text-gray-700 bg-white'
                  }`}
                  onClick={() => handleRangeSelect(range)}
                >
                  {range}
                </button>
              ))}
              <div className="h-9 w-9 rounded-lg border border-gray-200 flex items-center justify-center text-gray-500">
                <Calendar className="h-4 w-4" />
              </div>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <div className="relative flex-1 min-w-[220px]">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
              <input
                type="text"
                placeholder="Search vendor or reference"
                value={search}
                onChange={(event) => {
                  setSearch(event.target.value);
                  setPage(1);
                }}
                className="pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#105E53] focus:border-transparent w-full"
              />
            </div>
            <div className="flex items-center gap-2">
              <Filter className="h-4 w-4 text-gray-500" />
              <select
                value={statusFilter}
                onChange={(event) => {
                  setStatusFilter(event.target.value as StatusFilter);
                  setPage(1);
                }}
                className="px-3 py-2 border border-gray-300 rounded-lg text-sm"
              >
                <option value="all">All Statuses</option>
                {Object.entries(STATUS_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </div>
            <div className="ml-auto text-sm text-gray-500">
              {loading ? 'Loading payouts...' : `${total} payouts`}
            </div>
          </div>
        </div>

        {selectedIds.length > 0 && (
          <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-4 flex flex-wrap items-center gap-3">
            <div className="text-sm font-semibold text-gray-700">
              {selectedIds.length} selected
            </div>
            <select
              value={bulkStatus}
              onChange={(event) => setBulkStatus(event.target.value as AdminPayoutStatus)}
              className="px-3 py-2 border border-gray-300 rounded-lg text-sm"
            >
              {Object.entries(STATUS_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
            <input
              type="text"
              value={bulkNotes}
              onChange={(event) => setBulkNotes(event.target.value)}
              className="flex-1 min-w-[200px] px-3 py-2 border border-gray-300 rounded-lg text-sm"
              placeholder="Optional notes"
            />
            <button
              type="button"
              onClick={handleBulkUpdate}
              className="px-4 py-2 rounded-lg bg-[#105E53] text-white text-sm font-semibold"
            >
              Apply
            </button>
            <button
              type="button"
              onClick={() => setSelectedIds([])}
              className="px-4 py-2 rounded-lg border border-gray-200 text-sm"
            >
              Clear
            </button>
          </div>
        )}

        <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-gray-600">
                <tr>
                  <th className="text-left px-5 py-3 font-semibold">
                    <input
                      type="checkbox"
                      checked={payouts.length > 0 && selectedIds.length === payouts.length}
                      onChange={handleSelectAll}
                      className="h-4 w-4"
                    />
                  </th>
                  <th className="text-left px-5 py-3 font-semibold">Vendor</th>
                  <th className="text-left px-5 py-3 font-semibold">Period</th>
                  <th className="text-left px-5 py-3 font-semibold">Total Sales</th>
                  <th className="text-left px-5 py-3 font-semibold">Commission</th>
                  <th className="text-left px-5 py-3 font-semibold">Payout</th>
                  <th className="text-left px-5 py-3 font-semibold">Status</th>
                  <th className="text-left px-5 py-3 font-semibold">Processed</th>
                  <th className="text-left px-5 py-3 font-semibold">Reference</th>
                  <th className="text-left px-5 py-3 font-semibold">Notes</th>
                  <th className="text-left px-5 py-3 font-semibold">Actions</th>
                </tr>
              </thead>
              <tbody>
                {payouts.map((payout) => (
                  <tr key={payout.id} className="border-t border-gray-100">
                    <td className="px-5 py-4">
                      <input
                        type="checkbox"
                        checked={selectedIds.includes(payout.id)}
                        onChange={() => handleSelectOne(payout.id)}
                        className="h-4 w-4"
                      />
                    </td>
                    <td className="px-5 py-4">
                      <div className="font-semibold text-gray-900">{payout.vendor.business_name}</div>
                      <div className="text-xs text-gray-500">{payout.vendor.email || '—'}</div>
                    </td>
                    <td className="px-5 py-4 text-gray-700">
                      {formatDate(payout.payout_period_start)} - {formatDate(payout.payout_period_end)}
                    </td>
                    <td className="px-5 py-4 text-gray-900 font-semibold">
                      {formatAmount(payout.total_sales)}
                    </td>
                    <td className="px-5 py-4 text-gray-700">
                      {formatAmount(payout.commission_amount)}
                    </td>
                    <td className="px-5 py-4 text-gray-900 font-semibold">
                      {formatAmount(payout.payout_amount)}
                    </td>
                    <td className="px-5 py-4">
                      <span className={`px-3 py-1 rounded-full text-xs font-semibold ${STATUS_BADGES[payout.status]}`}>
                        {STATUS_LABELS[payout.status]}
                      </span>
                    </td>
                    <td className="px-5 py-4 text-gray-700">{formatDate(payout.processed_at)}</td>
                    <td className="px-5 py-4">
                      <input
                        type="text"
                        value={rowEdits[payout.id]?.payment_reference || ''}
                        onChange={(event) =>
                          handleEditChange(payout.id, { payment_reference: event.target.value })
                        }
                        className="w-40 px-2 py-1 border border-gray-200 rounded-md text-xs"
                        placeholder="Reference"
                      />
                    </td>
                    <td className="px-5 py-4">
                      <input
                        type="text"
                        value={rowEdits[payout.id]?.notes || ''}
                        onChange={(event) => handleEditChange(payout.id, { notes: event.target.value })}
                        className="w-48 px-2 py-1 border border-gray-200 rounded-md text-xs"
                        placeholder="Notes"
                      />
                    </td>
                    <td className="px-5 py-4">
                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          onClick={() => openAccountDetails(payout.id)}
                          className="h-8 w-8 rounded-full border border-gray-200 flex items-center justify-center text-gray-600 hover:text-[#105E53] hover:border-[#105E53] transition-colors"
                          title="View account details"
                        >
                          <Eye className="h-4 w-4" />
                        </button>
                        <select
                          value={rowEdits[payout.id]?.status || payout.status}
                          onChange={(event) =>
                            handleEditChange(payout.id, { status: event.target.value as AdminPayoutStatus })
                          }
                          className="px-2 py-1 border border-gray-200 rounded-md text-xs"
                        >
                          {Object.entries(STATUS_LABELS).map(([value, label]) => (
                            <option key={value} value={value}>
                              {label}
                            </option>
                          ))}
                        </select>
                        <button
                          type="button"
                          onClick={() => handleUpdate(payout.id)}
                          disabled={saving[payout.id]}
                          className="px-3 py-1.5 rounded-md bg-[#105E53] text-white text-xs font-semibold disabled:opacity-50"
                        >
                          {saving[payout.id] ? 'Saving...' : 'Update'}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
                {!loading && payouts.length === 0 && (
                  <tr>
                    <td colSpan={11} className="px-5 py-10 text-center text-sm text-gray-500">
                      No payouts found for the selected filters.
                    </td>
                  </tr>
                )}
                {loading && (
                  <tr>
                    <td colSpan={11} className="px-5 py-10 text-center text-sm text-gray-500">
                      Loading payouts...
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          <div className="flex items-center justify-between px-5 py-4 border-t border-gray-100 text-sm text-gray-600">
            <span>
              Page {page} of {totalPages}
            </span>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setPage((prev) => Math.max(prev - 1, 1))}
                disabled={page === 1 || loading}
                className="px-3 py-1.5 rounded-md border border-gray-200 text-xs disabled:opacity-50"
              >
                Previous
              </button>
              <button
                type="button"
                onClick={() => setPage((prev) => Math.min(prev + 1, totalPages))}
                disabled={page >= totalPages || loading}
                className="px-3 py-1.5 rounded-md border border-gray-200 text-xs disabled:opacity-50"
              >
                Next
              </button>
            </div>
          </div>
        </div>

        {detailsPayoutId && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
            <div className="bg-white w-full max-w-lg rounded-2xl shadow-xl p-6 relative">
              <button
                type="button"
                onClick={closeAccountDetails}
                className="absolute right-4 top-4 text-gray-400 hover:text-gray-600"
              >
                ×
              </button>
              <div className="space-y-4">
                <div>
                  <h2 className="text-lg font-semibold text-gray-900">Vendor Account Details</h2>
                  <p className="text-sm text-gray-500">
                    {selectedPayout?.vendor.business_name || accountDetails?.vendor_name || 'Vendor'}
                  </p>
                </div>
                {accountLoading && (
                  <div className="text-sm text-gray-500">Loading account details...</div>
                )}
                {accountError && (
                  <div className="text-sm text-rose-500">{accountError}</div>
                )}
                {accountDetails && !accountLoading && (
                  <div className="grid grid-cols-2 gap-4 text-sm">
                    <div>
                      <div className="text-gray-500">Bank Name</div>
                      <div className="font-semibold text-gray-900">{accountDetails.bank_name}</div>
                    </div>
                    <div>
                      <div className="text-gray-500">Account Number</div>
                      <div className="font-semibold text-gray-900">{accountDetails.account_number}</div>
                    </div>
                    <div>
                      <div className="text-gray-500">Account Holder</div>
                      <div className="font-semibold text-gray-900">{accountDetails.account_holder}</div>
                    </div>
                    <div>
                      <div className="text-gray-500">Account Type</div>
                      <div className="font-semibold text-gray-900">
                        {accountDetails.account_type || '—'}
                      </div>
                    </div>
                    <div>
                      <div className="text-gray-500">Default Method</div>
                      <div className="font-semibold text-gray-900">
                        {accountDetails.is_default ? 'Yes' : 'No'}
                      </div>
                    </div>
                    <div>
                      <div className="text-gray-500">Source</div>
                      <div className="font-semibold text-gray-900">
                        {accountDetails.source === 'payment_method' ? 'Payment method' : 'Vendor profile'}
                      </div>
                    </div>
                  </div>
                )}
                <div className="pt-2 flex justify-end">
                  <button
                    type="button"
                    onClick={closeAccountDetails}
                    className="px-4 py-2 rounded-lg border border-gray-200 text-sm text-gray-700"
                  >
                    Close
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
