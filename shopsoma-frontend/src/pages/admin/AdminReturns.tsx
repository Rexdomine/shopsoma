import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import AdminSidebar from '../../components/admin/AdminSidebar';
import { ROUTES } from '../../config/constants';
import {
  listAdminReturns,
  type AdminReturnListItem,
  type AdminReturnFilters,
  type ReturnStatus,
} from '../../services/adminReturnService';
import { useToast } from '../../hooks/useToast';

const STATUS_OPTIONS: Array<{ label: string; value: ReturnStatus | '' }> = [
  { label: 'All', value: '' },
  { label: 'Requested', value: 'requested' },
  { label: 'Approved', value: 'approved' },
  { label: 'Rejected', value: 'rejected' },
  { label: 'Received', value: 'received' },
  { label: 'Refunded', value: 'refunded' },
];

export default function AdminReturns() {
  const navigate = useNavigate();
  const { error } = useToast();
  const [returns, setReturns] = useState<AdminReturnListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);
  const [totalPages, setTotalPages] = useState(0);
  const [total, setTotal] = useState(0);
  const [filters, setFilters] = useState<AdminReturnFilters>({});

  const loadReturns = useCallback(async () => {
    try {
      setLoading(true);
      const data = await listAdminReturns({ page, page_size: pageSize, ...filters });
      setReturns(data.returns);
      setTotal(data.total);
      setTotalPages(data.total_pages);
    } catch (err) {
      console.error('Failed to load returns', err);
      error('Failed to load return requests');
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, filters, error]);

  useEffect(() => {
    loadReturns();
  }, [loadReturns]);

  const handleStatusChange = (value: ReturnStatus | '') => {
    setFilters((prev) => ({ ...prev, status: value || undefined }));
    setPage(1);
  };

  const handleSearchChange = (value: string) => {
    setFilters((prev) => ({ ...prev, search: value || undefined }));
    setPage(1);
  };

  const statusBadge = (status: ReturnStatus) => {
    switch (status) {
      case 'requested':
        return 'bg-amber-50 text-amber-700 border border-amber-200';
      case 'approved':
      case 'received':
      case 'refunded':
        return 'bg-emerald-50 text-emerald-700 border border-emerald-200';
      case 'rejected':
        return 'bg-red-50 text-red-700 border border-red-200';
      default:
        return 'bg-gray-100 text-gray-600 border border-gray-200';
    }
  };

  const paginationLabel = useMemo(() => {
    if (!total) return '0 returns';
    return `${total} return${total === 1 ? '' : 's'}`;
  }, [total]);

  return (
    <div className="min-h-screen bg-[var(--color-page-bg)] flex">
      <AdminSidebar activeSection="returns" />

      <main className="flex-1 p-8 space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold text-gray-900">Return Requests</h1>
            <p className="mt-1 text-sm text-gray-500">Review, approve, and manage customer return requests</p>
          </div>
        </div>

        <div className="bg-white rounded-lg shadow p-6 space-y-4">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            <div className="flex flex-wrap gap-3">
              {STATUS_OPTIONS.map((option) => (
                <button
                  key={option.label}
                  type="button"
                  onClick={() => handleStatusChange(option.value)}
                  className={`px-4 py-1.5 rounded-full text-xs uppercase tracking-[0.3em] border transition ${
                    (filters.status || '') === option.value
                      ? 'border-[#105E53] text-[#105E53] bg-[#105E53]/10'
                      : 'border-gray-200 text-gray-500 hover:border-[#105E53]/40'
                  }`}
                >
                  {option.label}
                </button>
              ))}
            </div>
            <div className="flex items-center gap-3">
              <input
                type="search"
                placeholder="Search return number, order, customer"
                onChange={(event) => handleSearchChange(event.target.value)}
                className="w-72 border border-gray-200 rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-[#105E53]"
              />
              <span className="text-xs text-gray-500">{paginationLabel}</span>
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead>
                <tr className="text-xs uppercase tracking-[0.2em] text-gray-400 border-b">
                  <th className="py-3 pr-3">Return</th>
                  <th className="py-3 pr-3">Customer</th>
                  <th className="py-3 pr-3">Product</th>
                  <th className="py-3 pr-3">Amount</th>
                  <th className="py-3 pr-3">Status</th>
                  <th className="py-3 text-right">Action</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr>
                    <td colSpan={6} className="py-10 text-center text-gray-500">
                      Loading returns...
                    </td>
                  </tr>
                ) : returns.length ? (
                  returns.map((item) => (
                    <tr key={item.id} className="border-b last:border-b-0">
                      <td className="py-4 pr-3">
                        <div className="font-semibold text-gray-900">{item.return_number}</div>
                        <div className="text-xs text-gray-500">Order: {item.order_number || '—'}</div>
                      </td>
                      <td className="py-4 pr-3">
                        <div className="font-semibold text-gray-900">{item.customer?.full_name || '—'}</div>
                        <div className="text-xs text-gray-500">{item.customer?.email || ''}</div>
                      </td>
                      <td className="py-4 pr-3">
                        <div className="font-semibold text-gray-900">{item.product_title || '—'}</div>
                        <div className="text-xs text-gray-500">Qty: {item.quantity ?? 1}</div>
                      </td>
                      <td className="py-4 pr-3">
                        ₦{(item.amount ?? 0).toLocaleString()}
                      </td>
                      <td className="py-4 pr-3">
                        <span className={`inline-flex px-3 py-1 rounded-sm text-xs font-semibold ${statusBadge(item.status)}`}>
                          {item.status}
                        </span>
                      </td>
                      <td className="py-4 text-right">
                        <button
                          type="button"
                          onClick={() => navigate(`${ROUTES.ADMIN_RETURNS}/${item.id}`)}
                          className="px-4 py-2 border border-[#105E53] text-[#105E53] text-xs uppercase tracking-[0.3em] rounded-sm hover:bg-[#105E53] hover:text-white transition"
                        >
                          View
                        </button>
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={6} className="py-10 text-center text-gray-500">
                      No return requests found.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          <div className="flex items-center justify-between">
            <button
              type="button"
              onClick={() => setPage((prev) => Math.max(prev - 1, 1))}
              disabled={page <= 1}
              className="px-4 py-2 border border-gray-200 text-xs uppercase tracking-[0.3em] rounded-sm disabled:opacity-50"
            >
              Previous
            </button>
            <div className="text-xs text-gray-500">Page {page} of {Math.max(totalPages, 1)}</div>
            <button
              type="button"
              onClick={() => setPage((prev) => Math.min(prev + 1, totalPages))}
              disabled={page >= totalPages}
              className="px-4 py-2 border border-gray-200 text-xs uppercase tracking-[0.3em] rounded-sm disabled:opacity-50"
            >
              Next
            </button>
          </div>
        </div>
      </main>
    </div>
  );
}
