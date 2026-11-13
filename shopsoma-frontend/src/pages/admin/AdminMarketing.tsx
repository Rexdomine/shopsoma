import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  CheckCircle2,
  Edit2,
  Plus,
  Search,
  Tag,
  Trash2,
  X,
  XCircle,
} from 'lucide-react';
import AdminSidebar from '../../components/admin/AdminSidebar';
import ToastContainer from '../../components/ui/ToastContainer';
import { useToast } from '../../hooks/useToast';
import {
  promoCodeService,
  type DiscountType,
  type PromoCode,
  type PromoCodeCreatePayload,
  type PromoCodeUpdatePayload,
} from '../../services/promoCodeService';

type StatusFilter = 'all' | 'active' | 'inactive' | 'scheduled' | 'expired';

interface PromoFormState {
  code: string;
  description: string;
  discount_type: DiscountType;
  discount_value: string;
  min_purchase_amount: string;
  max_discount_amount: string;
  usage_limit: string;
  usage_limit_per_user: string;
  valid_from: string;
  valid_until: string;
  is_active: boolean;
}

function toDatetimeLocalValue(isoOrDate: Date | string): string {
  const date = typeof isoOrDate === 'string' ? new Date(isoOrDate) : isoOrDate;
  if (Number.isNaN(date.getTime())) {
    return '';
  }
  const offsetMinutes = date.getTimezoneOffset();
  const local = new Date(date.getTime() - offsetMinutes * 60_000);
  return local.toISOString().slice(0, 16);
}

function defaultFormState(): PromoFormState {
  const now = new Date();
  const nextMonth = new Date(now.getTime() + 30 * 24 * 60 * 60 * 1000);
  return {
    code: '',
    description: '',
    discount_type: 'percentage',
    discount_value: '10',
    min_purchase_amount: '0',
    max_discount_amount: '',
    usage_limit: '',
    usage_limit_per_user: '1',
    valid_from: toDatetimeLocalValue(now),
    valid_until: toDatetimeLocalValue(nextMonth),
    is_active: true,
  };
}

function getPromoLifecycleStatus(promo: PromoCode, nowMs: number = Date.now()): Exclude<StatusFilter, 'all'> {
  if (!promo.is_active) {
    return 'inactive';
  }
  const startMs = new Date(promo.valid_from).getTime();
  const endMs = new Date(promo.valid_until).getTime();
  if (!Number.isNaN(startMs) && nowMs < startMs) {
    return 'scheduled';
  }
  if (!Number.isNaN(endMs) && nowMs > endMs) {
    return 'expired';
  }
  return 'active';
}

function formatNgn(amount: number): string {
  return `₦${Number(amount || 0).toLocaleString('en-NG', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  })}`;
}

function formatDateTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return '—';
  }
  return date.toLocaleString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function extractErrorMessage(err: unknown, fallback: string): string {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (typeof detail === 'string' && detail.trim()) {
    return detail;
  }
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0] as { msg?: string };
    if (first?.msg) {
      return first.msg;
    }
  }
  if (err instanceof Error && err.message) {
    return err.message;
  }
  return fallback;
}

export default function AdminMarketing() {
  const { toasts, hideToast, success, error } = useToast();

  const [promoCodes, setPromoCodes] = useState<PromoCode[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');

  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingPromo, setEditingPromo] = useState<PromoCode | null>(null);
  const [form, setForm] = useState<PromoFormState>(defaultFormState);
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const [togglingId, setTogglingId] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<PromoCode | null>(null);
  const [deleting, setDeleting] = useState(false);

  const fetchPromoCodes = useCallback(async () => {
    try {
      setLoading(true);
      const res = await promoCodeService.listPromoCodes();
      setPromoCodes(res.promo_codes || []);
    } catch (err) {
      console.error('Failed to load promo codes:', err);
      error(extractErrorMessage(err, 'Failed to load discount codes'));
    } finally {
      setLoading(false);
    }
  }, [error]);

  useEffect(() => {
    void fetchPromoCodes();
  }, [fetchPromoCodes]);

  const stats = useMemo(() => {
    const nowMs = Date.now();
    let active = 0;
    let scheduled = 0;
    let expired = 0;
    let inactive = 0;
    let totalRedemptions = 0;

    for (const promo of promoCodes) {
      totalRedemptions += promo.usage_count || 0;
      const lifecycle = getPromoLifecycleStatus(promo, nowMs);
      if (lifecycle === 'active') active += 1;
      else if (lifecycle === 'scheduled') scheduled += 1;
      else if (lifecycle === 'expired') expired += 1;
      else inactive += 1;
    }

    return {
      total: promoCodes.length,
      active,
      scheduled,
      expired,
      inactive,
      totalRedemptions,
    };
  }, [promoCodes]);

  const filteredPromoCodes = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    const nowMs = Date.now();
    return promoCodes.filter((promo) => {
      const lifecycle = getPromoLifecycleStatus(promo, nowMs);
      if (statusFilter !== 'all' && lifecycle !== statusFilter) {
        return false;
      }
      if (!query) {
        return true;
      }
      return (
        promo.code.toLowerCase().includes(query) ||
        (promo.description || '').toLowerCase().includes(query)
      );
    });
  }, [promoCodes, searchQuery, statusFilter]);

  const openCreateModal = () => {
    setEditingPromo(null);
    setForm(defaultFormState());
    setFormError(null);
    setIsModalOpen(true);
  };

  const openEditModal = (promo: PromoCode) => {
    setEditingPromo(promo);
    setForm({
      code: promo.code,
      description: promo.description || '',
      discount_type: promo.discount_type,
      discount_value: String(promo.discount_value),
      min_purchase_amount: promo.min_purchase_amount != null ? String(promo.min_purchase_amount) : '0',
      max_discount_amount: promo.max_discount_amount != null ? String(promo.max_discount_amount) : '',
      usage_limit: promo.usage_limit != null ? String(promo.usage_limit) : '',
      usage_limit_per_user: String(promo.usage_limit_per_user ?? 1),
      valid_from: toDatetimeLocalValue(promo.valid_from),
      valid_until: toDatetimeLocalValue(promo.valid_until),
      is_active: promo.is_active,
    });
    setFormError(null);
    setIsModalOpen(true);
  };

  const closeModal = () => {
    if (saving) return;
    setIsModalOpen(false);
    setEditingPromo(null);
    setFormError(null);
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);

    const normalizedCode = form.code.trim().toUpperCase();
    if (normalizedCode.length < 3) {
      setFormError('Promo code must be at least 3 characters.');
      return;
    }

    const discountValue = Number(form.discount_value);
    if (!Number.isFinite(discountValue) || discountValue <= 0) {
      setFormError('Discount value must be greater than 0.');
      return;
    }
    if (form.discount_type === 'percentage' && discountValue > 100) {
      setFormError('Percentage discount cannot exceed 100%.');
      return;
    }

    const minPurchase = form.min_purchase_amount.trim() ? Number(form.min_purchase_amount) : 0;
    if (!Number.isFinite(minPurchase) || minPurchase < 0) {
      setFormError('Minimum purchase amount cannot be negative.');
      return;
    }

    const maxDiscount =
      form.discount_type === 'percentage' && form.max_discount_amount.trim()
        ? Number(form.max_discount_amount)
        : null;
    if (maxDiscount !== null && (!Number.isFinite(maxDiscount) || maxDiscount < 0)) {
      setFormError('Maximum discount cap cannot be negative.');
      return;
    }

    const usageLimit = form.usage_limit.trim() ? Number(form.usage_limit) : null;
    if (usageLimit !== null && (!Number.isInteger(usageLimit) || usageLimit < 1)) {
      setFormError('Total usage limit must be a whole number of at least 1.');
      return;
    }

    const perUserLimit = form.usage_limit_per_user.trim() ? Number(form.usage_limit_per_user) : 1;
    if (!Number.isInteger(perUserLimit) || perUserLimit < 1) {
      setFormError('Per-user limit must be a whole number of at least 1.');
      return;
    }

    const validFromDate = new Date(form.valid_from);
    const validUntilDate = new Date(form.valid_until);
    if (Number.isNaN(validFromDate.getTime()) || Number.isNaN(validUntilDate.getTime())) {
      setFormError('Valid from and valid until dates are required.');
      return;
    }
    if (validUntilDate <= validFromDate) {
      setFormError('Valid until must be later than valid from.');
      return;
    }

    const payload: PromoCodeCreatePayload = {
      code: normalizedCode,
      description: form.description.trim() || null,
      discount_type: form.discount_type,
      discount_value: discountValue,
      min_purchase_amount: minPurchase,
      max_discount_amount: maxDiscount,
      usage_limit: usageLimit,
      usage_limit_per_user: perUserLimit,
      valid_from: validFromDate.toISOString(),
      valid_until: validUntilDate.toISOString(),
      is_active: form.is_active,
    };

    try {
      setSaving(true);
      if (editingPromo) {
        const updatePayload: PromoCodeUpdatePayload = { ...payload };
        const updated = await promoCodeService.updatePromoCode(editingPromo.id, updatePayload);
        setPromoCodes((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
        success(`Discount code ${updated.code} updated`);
      } else {
        const created = await promoCodeService.createPromoCode(payload);
        setPromoCodes((prev) => [created, ...prev]);
        success(`Discount code ${created.code} created`);
      }
      setIsModalOpen(false);
      setEditingPromo(null);
    } catch (err) {
      console.error('Failed to save promo code:', err);
      setFormError(extractErrorMessage(err, 'Failed to save discount code'));
    } finally {
      setSaving(false);
    }
  };

  const handleToggleActive = async (promo: PromoCode) => {
    try {
      setTogglingId(promo.id);
      const updated = await promoCodeService.updatePromoCode(promo.id, {
        is_active: !promo.is_active,
      });
      setPromoCodes((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
      success(
        updated.is_active
          ? `Discount code ${updated.code} activated`
          : `Discount code ${updated.code} deactivated`
      );
    } catch (err) {
      console.error('Failed to update promo status:', err);
      error(extractErrorMessage(err, 'Failed to update promo status'));
    } finally {
      setTogglingId(null);
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    try {
      setDeleting(true);
      await promoCodeService.deletePromoCode(deleteTarget.id);
      setPromoCodes((prev) => prev.filter((item) => item.id !== deleteTarget.id));
      success(`Discount code ${deleteTarget.code} deleted`);
      setDeleteTarget(null);
    } catch (err) {
      console.error('Failed to delete promo code:', err);
      error(extractErrorMessage(err, 'Failed to delete discount code'));
    } finally {
      setDeleting(false);
    }
  };

  const renderStatusBadge = (promo: PromoCode) => {
    const lifecycle = getPromoLifecycleStatus(promo);
    if (lifecycle === 'active') {
      return (
        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-50 text-emerald-700 border border-emerald-200">
          <CheckCircle2 className="w-3.5 h-3.5" />
          Active
        </span>
      );
    }
    if (lifecycle === 'scheduled') {
      return (
        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-50 text-blue-700 border border-blue-200">
          Scheduled
        </span>
      );
    }
    if (lifecycle === 'expired') {
      return (
        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-amber-50 text-amber-700 border border-amber-200">
          Expired
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-700 border border-gray-200">
        <XCircle className="w-3.5 h-3.5" />
        Inactive
      </span>
    );
  };

  return (
    <div className="flex flex-col md:flex-row min-h-screen bg-[var(--color-page-bg)] w-full overflow-x-hidden">
      <AdminSidebar activeSection="marketing" />

      <main className="flex-1 min-w-0 p-4 sm:p-6 lg:p-8 space-y-6">
        <ToastContainer toasts={toasts} onClose={hideToast} />

        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl sm:text-3xl font-bold text-gray-900">Marketing & Discount Codes</h1>
            <p className="mt-1 text-xs sm:text-sm text-gray-500">
              Create and manage platform-wide promo codes used in customer checkout
            </p>
          </div>
          <button
            type="button"
            onClick={openCreateModal}
            className="inline-flex items-center justify-center gap-2 px-4 py-2.5 bg-primary text-white text-sm font-medium rounded-lg hover:bg-primary/90 transition-colors"
          >
            <Plus className="w-4 h-4" />
            Create Discount Code
          </button>
        </div>

        {/* Summary Cards */}
        <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
          <div className="bg-white rounded-xl border border-gray-200 p-4">
            <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">Total Codes</p>
            <p className="mt-2 text-2xl font-semibold text-gray-900">{stats.total}</p>
          </div>
          <div className="bg-white rounded-xl border border-gray-200 p-4">
            <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">Active Now</p>
            <p className="mt-2 text-2xl font-semibold text-emerald-700">{stats.active}</p>
          </div>
          <div className="bg-white rounded-xl border border-gray-200 p-4">
            <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">Scheduled</p>
            <p className="mt-2 text-2xl font-semibold text-blue-700">{stats.scheduled}</p>
          </div>
          <div className="bg-white rounded-xl border border-gray-200 p-4">
            <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">Expired</p>
            <p className="mt-2 text-2xl font-semibold text-amber-700">{stats.expired}</p>
          </div>
          <div className="bg-white rounded-xl border border-gray-200 p-4 col-span-2 lg:col-span-1">
            <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">Redemptions</p>
            <p className="mt-2 text-2xl font-semibold text-gray-900">{stats.totalRedemptions}</p>
          </div>
        </div>

        {/* Filter & Search Bar */}
        <div className="bg-white rounded-xl border border-gray-200 p-4 flex flex-col lg:flex-row lg:items-center justify-between gap-4">
          <div className="flex flex-wrap items-center gap-2">
            {(
              [
                { key: 'all', label: `All (${stats.total})` },
                { key: 'active', label: `Active (${stats.active})` },
                { key: 'scheduled', label: `Scheduled (${stats.scheduled})` },
                { key: 'expired', label: `Expired (${stats.expired})` },
                { key: 'inactive', label: `Inactive (${stats.inactive})` },
              ] as const
            ).map((tab) => (
              <button
                key={tab.key}
                type="button"
                onClick={() => setStatusFilter(tab.key)}
                className={`px-3 py-1.5 rounded-lg text-xs sm:text-sm font-medium transition-colors ${
                  statusFilter === tab.key
                    ? 'bg-primary text-white'
                    : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          <div className="relative w-full lg:w-72">
            <Search className="w-4 h-4 text-gray-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search code or description..."
              className="w-full pl-9 pr-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary"
            />
          </div>
        </div>

        {/* Table */}
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          {loading ? (
            <div className="p-12 text-center text-sm text-gray-500">Loading discount codes...</div>
          ) : filteredPromoCodes.length === 0 ? (
            <div className="p-12 text-center space-y-3">
              <div className="mx-auto w-12 h-12 rounded-full bg-primary/10 text-primary flex items-center justify-center">
                <Tag className="w-6 h-6" />
              </div>
              <p className="text-base font-medium text-gray-900">
                {promoCodes.length === 0 ? 'No discount codes yet' : 'No matching discount codes'}
              </p>
              <p className="text-sm text-gray-500 max-w-md mx-auto">
                {promoCodes.length === 0
                  ? 'Create your first promo code so customers can apply it at checkout.'
                  : 'Try adjusting your search query or status filter.'}
              </p>
              {promoCodes.length === 0 && (
                <button
                  type="button"
                  onClick={openCreateModal}
                  className="inline-flex items-center gap-2 px-4 py-2 bg-primary text-white text-sm font-medium rounded-lg hover:bg-primary/90"
                >
                  <Plus className="w-4 h-4" />
                  Create Discount Code
                </button>
              )}
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200 text-sm">
                <thead className="bg-gray-50 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">
                  <tr>
                    <th className="px-4 py-3">Code</th>
                    <th className="px-4 py-3">Discount</th>
                    <th className="px-4 py-3">Rules</th>
                    <th className="px-4 py-3">Usage</th>
                    <th className="px-4 py-3">Validity Window</th>
                    <th className="px-4 py-3">Status</th>
                    <th className="px-4 py-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200">
                  {filteredPromoCodes.map((promo) => (
                    <tr key={promo.id} className="hover:bg-gray-50/70">
                      <td className="px-4 py-3.5 align-top">
                        <div className="font-mono font-semibold text-gray-900">{promo.code}</div>
                        {promo.description && (
                          <div className="text-xs text-gray-500 mt-0.5 max-w-xs">{promo.description}</div>
                        )}
                      </td>
                      <td className="px-4 py-3.5 align-top">
                        <div className="font-medium text-gray-900">
                          {promo.discount_type === 'percentage'
                            ? `${Number(promo.discount_value)}% off`
                            : `${formatNgn(Number(promo.discount_value))} off`}
                        </div>
                        {promo.discount_type === 'percentage' &&
                          promo.max_discount_amount != null &&
                          Number(promo.max_discount_amount) > 0 && (
                            <div className="text-xs text-gray-500 mt-0.5">
                              Max cap: {formatNgn(Number(promo.max_discount_amount))}
                            </div>
                          )}
                      </td>
                      <td className="px-4 py-3.5 align-top text-xs text-gray-600 space-y-0.5">
                        <div>
                          Min order:{' '}
                          {promo.min_purchase_amount && Number(promo.min_purchase_amount) > 0
                            ? formatNgn(Number(promo.min_purchase_amount))
                            : 'None'}
                        </div>
                        <div>Per customer: {promo.usage_limit_per_user}</div>
                      </td>
                      <td className="px-4 py-3.5 align-top text-xs text-gray-700">
                        <span className="font-medium text-gray-900">{promo.usage_count}</span>
                        {' / '}
                        {promo.usage_limit != null ? promo.usage_limit : 'Unlimited'}
                      </td>
                      <td className="px-4 py-3.5 align-top text-xs text-gray-600 space-y-0.5 whitespace-nowrap">
                        <div>From: {formatDateTime(promo.valid_from)}</div>
                        <div>Until: {formatDateTime(promo.valid_until)}</div>
                      </td>
                      <td className="px-4 py-3.5 align-top">
                        <div className="flex flex-col items-start gap-1.5">
                          {renderStatusBadge(promo)}
                          <button
                            type="button"
                            onClick={() => void handleToggleActive(promo)}
                            disabled={togglingId === promo.id}
                            className="text-xs font-medium text-primary hover:underline disabled:opacity-50"
                          >
                            {togglingId === promo.id
                              ? 'Updating...'
                              : promo.is_active
                                ? 'Deactivate'
                                : 'Activate'}
                          </button>
                        </div>
                      </td>
                      <td className="px-4 py-3.5 align-top text-right whitespace-nowrap">
                        <div className="inline-flex items-center gap-2">
                          <button
                            type="button"
                            onClick={() => openEditModal(promo)}
                            aria-label={`Edit ${promo.code}`}
                            className="p-1.5 text-gray-600 hover:text-primary hover:bg-gray-100 rounded-lg transition-colors"
                          >
                            <Edit2 className="w-4 h-4" />
                          </button>
                          <button
                            type="button"
                            onClick={() => setDeleteTarget(promo)}
                            aria-label={`Delete ${promo.code}`}
                            className="p-1.5 text-gray-600 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Create / Edit Modal */}
        {isModalOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 overflow-y-auto">
            <div className="bg-white rounded-xl border border-gray-200 w-full max-w-xl shadow-xl my-8">
              <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
                <h2 className="text-lg font-semibold text-gray-900">
                  {editingPromo ? `Edit Discount Code (${editingPromo.code})` : 'Create Discount Code'}
                </h2>
                <button
                  type="button"
                  onClick={closeModal}
                  aria-label="Close modal"
                  className="p-1 text-gray-400 hover:text-gray-600 rounded-lg"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>

              <form onSubmit={handleSave} className="p-6 space-y-4">
                {formError && (
                  <div className="p-3 rounded-lg bg-red-50 border border-red-200 text-sm text-red-700">
                    {formError}
                  </div>
                )}

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <label htmlFor="promo-code-input" className="block text-xs font-medium text-gray-700 mb-1">
                      Promo Code *
                    </label>
                    <input
                      id="promo-code-input"
                      type="text"
                      required
                      minLength={3}
                      maxLength={50}
                      value={form.code}
                      onChange={(e) =>
                        setForm((prev) => ({ ...prev, code: e.target.value.toUpperCase() }))
                      }
                      placeholder="e.g. WELCOME10"
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm font-mono uppercase focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary"
                    />
                  </div>

                  <div>
                    <label htmlFor="promo-type-select" className="block text-xs font-medium text-gray-700 mb-1">
                      Discount Type *
                    </label>
                    <select
                      id="promo-type-select"
                      value={form.discount_type}
                      onChange={(e) =>
                        setForm((prev) => ({
                          ...prev,
                          discount_type: e.target.value as DiscountType,
                        }))
                      }
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary"
                    >
                      <option value="percentage">Percentage (%)</option>
                      <option value="fixed_amount">Fixed Amount (NGN)</option>
                    </select>
                  </div>
                </div>

                <div>
                  <label htmlFor="promo-description-input" className="block text-xs font-medium text-gray-700 mb-1">
                    Description
                  </label>
                  <input
                    id="promo-description-input"
                    type="text"
                    maxLength={500}
                    value={form.description}
                    onChange={(e) => setForm((prev) => ({ ...prev, description: e.target.value }))}
                    placeholder="Internal or campaign note (e.g. First order welcome discount)"
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary"
                  />
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                  <div>
                    <label htmlFor="promo-value-input" className="block text-xs font-medium text-gray-700 mb-1">
                      {form.discount_type === 'percentage' ? 'Discount (%) *' : 'Discount Amount (₦) *'}
                    </label>
                    <input
                      id="promo-value-input"
                      type="number"
                      step="0.01"
                      min="0.01"
                      max={form.discount_type === 'percentage' ? '100' : undefined}
                      required
                      value={form.discount_value}
                      onChange={(e) => setForm((prev) => ({ ...prev, discount_value: e.target.value }))}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary"
                    />
                  </div>

                  <div>
                    <label htmlFor="promo-min-input" className="block text-xs font-medium text-gray-700 mb-1">
                      Min Purchase (₦)
                    </label>
                    <input
                      id="promo-min-input"
                      type="number"
                      step="0.01"
                      min="0"
                      value={form.min_purchase_amount}
                      onChange={(e) =>
                        setForm((prev) => ({ ...prev, min_purchase_amount: e.target.value }))
                      }
                      placeholder="0"
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary"
                    />
                  </div>

                  {form.discount_type === 'percentage' && (
                    <div>
                      <label htmlFor="promo-max-input" className="block text-xs font-medium text-gray-700 mb-1">
                        Max Discount Cap (₦)
                      </label>
                      <input
                        id="promo-max-input"
                        type="number"
                        step="0.01"
                        min="0"
                        value={form.max_discount_amount}
                        onChange={(e) =>
                          setForm((prev) => ({ ...prev, max_discount_amount: e.target.value }))
                        }
                        placeholder="No cap"
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary"
                      />
                    </div>
                  )}
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <label htmlFor="promo-usage-limit-input" className="block text-xs font-medium text-gray-700 mb-1">
                      Total Usage Limit
                    </label>
                    <input
                      id="promo-usage-limit-input"
                      type="number"
                      min="1"
                      step="1"
                      value={form.usage_limit}
                      onChange={(e) => setForm((prev) => ({ ...prev, usage_limit: e.target.value }))}
                      placeholder="Unlimited"
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary"
                    />
                  </div>

                  <div>
                    <label htmlFor="promo-per-user-input" className="block text-xs font-medium text-gray-700 mb-1">
                      Usage Limit Per Customer *
                    </label>
                    <input
                      id="promo-per-user-input"
                      type="number"
                      min="1"
                      step="1"
                      required
                      value={form.usage_limit_per_user}
                      onChange={(e) =>
                        setForm((prev) => ({ ...prev, usage_limit_per_user: e.target.value }))
                      }
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <label htmlFor="promo-valid-from" className="block text-xs font-medium text-gray-700 mb-1">
                      Valid From *
                    </label>
                    <input
                      id="promo-valid-from"
                      type="datetime-local"
                      required
                      value={form.valid_from}
                      onChange={(e) => setForm((prev) => ({ ...prev, valid_from: e.target.value }))}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary"
                    />
                  </div>

                  <div>
                    <label htmlFor="promo-valid-until" className="block text-xs font-medium text-gray-700 mb-1">
                      Valid Until *
                    </label>
                    <input
                      id="promo-valid-until"
                      type="datetime-local"
                      required
                      value={form.valid_until}
                      onChange={(e) => setForm((prev) => ({ ...prev, valid_until: e.target.value }))}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary"
                    />
                  </div>
                </div>

                <label className="inline-flex items-center gap-2 text-sm text-gray-700 pt-1 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={form.is_active}
                    onChange={(e) => setForm((prev) => ({ ...prev, is_active: e.target.checked }))}
                    className="rounded border-gray-300 text-primary focus:ring-primary"
                  />
                  Active immediately (customers can redeem during validity window)
                </label>

                <div className="flex items-center justify-end gap-3 pt-4 border-t border-gray-200">
                  <button
                    type="button"
                    onClick={closeModal}
                    disabled={saving}
                    className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={saving}
                    className="px-4 py-2 text-sm font-medium text-white bg-primary rounded-lg hover:bg-primary/90 disabled:opacity-50"
                  >
                    {saving ? 'Saving...' : editingPromo ? 'Save Changes' : 'Create Code'}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}

        {/* Delete Confirmation Modal */}
        {deleteTarget && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
            <div className="bg-white rounded-xl border border-gray-200 w-full max-w-md shadow-xl p-6 space-y-4">
              <h2 className="text-lg font-semibold text-gray-900">Delete Discount Code</h2>
              <p className="text-sm text-gray-600">
                Are you sure you want to delete{' '}
                <span className="font-mono font-semibold text-gray-900">{deleteTarget.code}</span>? Existing
                paid orders retain their historical promo code string, while customers will no longer be able
                to apply this code.
              </p>
              <div className="flex items-center justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setDeleteTarget(null)}
                  disabled={deleting}
                  className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={() => void handleDelete()}
                  disabled={deleting}
                  className="px-4 py-2 text-sm font-medium text-white bg-red-600 rounded-lg hover:bg-red-700 disabled:opacity-50"
                >
                  {deleting ? 'Deleting...' : 'Delete Code'}
                </button>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
