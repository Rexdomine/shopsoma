import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import AdminSidebar from '../../components/admin/AdminSidebar';
import { ROUTES } from '../../config/constants';
import {
  getAdminReturn,
  updateAdminReturnNotes,
  updateAdminReturnStatus,
  type AdminReturnDetail,
  type ReturnStatus,
} from '../../services/adminReturnService';
import { useToast } from '../../hooks/useToast';

const STATUS_OPTIONS: ReturnStatus[] = ['requested', 'approved', 'rejected', 'received', 'refunded'];

export default function AdminReturnDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { success, error } = useToast();
  const [returnDetail, setReturnDetail] = useState<AdminReturnDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [toastVisible, setToastVisible] = useState(false);
  const [toastMessage, setToastMessage] = useState('');
  const [toastTone, setToastTone] = useState<'success' | 'error'>('success');
  const [status, setStatus] = useState<ReturnStatus>('requested');
  const [adminNotes, setAdminNotes] = useState('');
  const [rejectionReason, setRejectionReason] = useState('');
  const [refundAmount, setRefundAmount] = useState('');
  const [refundMethod, setRefundMethod] = useState('');

  useEffect(() => {
    let isMounted = true;

    const loadDetail = async () => {
      if (!id) return;
      try {
        setLoading(true);
        const data = await getAdminReturn(id);
        if (!isMounted) return;
        setReturnDetail(data);
        setStatus(data.status);
        setAdminNotes(data.admin_notes || '');
        setRejectionReason(data.rejection_reason || '');
        setRefundAmount(data.refund_amount ? String(data.refund_amount) : '');
        setRefundMethod(data.refund_method || '');
      } catch (err) {
        console.error('Failed to load return', err);
        error('Failed to load return request');
      } finally {
        if (isMounted) setLoading(false);
      }
    };

    loadDetail();
    return () => {
      isMounted = false;
    };
  }, [id, error]);

  const formattedOrderDate = useMemo(() => {
    if (!returnDetail?.order_date) return '—';
    const parsed = new Date(returnDetail.order_date);
    if (Number.isNaN(parsed.getTime())) return '—';
    return parsed.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
  }, [returnDetail?.order_date]);

  const handleUpdateStatus = async () => {
    if (!id) return;
    try {
      setSaving(true);
      const updated = await updateAdminReturnStatus(id, {
        status,
        admin_notes: adminNotes || undefined,
        rejection_reason: rejectionReason || undefined,
        refund_amount: refundAmount ? Number(refundAmount) : undefined,
        refund_method: refundMethod || undefined,
      });
      setReturnDetail(updated);
      success('Return status updated');
      setToastMessage('Return status updated successfully');
      setToastTone('success');
      setToastVisible(true);
      setTimeout(() => setToastVisible(false), 4000);
    } catch (err) {
      console.error('Failed to update status', err);
      error('Failed to update return status');
      setToastMessage('Failed to update return status');
      setToastTone('error');
      setToastVisible(true);
      setTimeout(() => setToastVisible(false), 4000);
    } finally {
      setSaving(false);
    }
  };

  const handleUpdateNotes = async () => {
    if (!id) return;
    try {
      setSaving(true);
      const updated = await updateAdminReturnNotes(id, { admin_notes: adminNotes || undefined });
      setReturnDetail(updated);
      success('Notes updated');
      setToastMessage('Notes updated successfully');
      setToastTone('success');
      setToastVisible(true);
      setTimeout(() => setToastVisible(false), 4000);
    } catch (err) {
      console.error('Failed to update notes', err);
      error('Failed to update notes');
      setToastMessage('Failed to update notes');
      setToastTone('error');
      setToastVisible(true);
      setTimeout(() => setToastVisible(false), 4000);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="min-h-screen bg-[var(--color-page-bg)] flex">
      <AdminSidebar activeSection="returns" />

      <main className="flex-1 p-8 space-y-6">
        {toastVisible && (
          <div className={`rounded-lg border px-4 py-3 text-sm ${toastTone === 'success' ? 'border-emerald-200 bg-emerald-50 text-emerald-800' : 'border-red-200 bg-red-50 text-red-700'}`}>
            {toastMessage}
          </div>
        )}
        <div className="flex items-center justify-between">
          <div>
            <button
              type="button"
              onClick={() => navigate(ROUTES.ADMIN_RETURNS)}
              className="text-xs uppercase tracking-[0.3em] text-gray-400"
            >
              ← Back to returns
            </button>
            <h1 className="text-3xl font-bold text-gray-900 mt-2">Return Request</h1>
          </div>
        </div>

        {loading ? (
          <div className="bg-white rounded-lg shadow p-10 text-center text-gray-500">Loading return...</div>
        ) : returnDetail ? (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2 space-y-6">
              <div className="bg-white rounded-lg shadow p-6 space-y-6">
                <div className="flex items-start gap-6">
                  <div className="h-24 w-24 rounded-lg border border-gray-200 overflow-hidden bg-gray-50">
                    {returnDetail.product_image_url ? (
                      <img
                        src={returnDetail.product_image_url}
                        alt={returnDetail.product_title || 'Return item'}
                        className="h-full w-full object-cover"
                      />
                    ) : (
                      <div className="h-full w-full flex items-center justify-center text-gray-400 text-xs">No Image</div>
                    )}
                  </div>
                  <div className="space-y-2">
                    <p className="text-xs uppercase tracking-[0.3em] text-gray-400">Return Number</p>
                    <p className="text-xl font-semibold text-gray-900">{returnDetail.return_number}</p>
                    <p className="text-sm text-gray-500">Order: {returnDetail.order_number || '—'}</p>
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-6 text-sm">
                  <div className="space-y-2">
                    <p className="text-xs uppercase tracking-[0.3em] text-gray-400">Product</p>
                    <p className="font-semibold text-gray-900">{returnDetail.product_title || '—'}</p>
                  </div>
                  <div className="space-y-2">
                    <p className="text-xs uppercase tracking-[0.3em] text-gray-400">Order Date</p>
                    <p className="font-semibold text-gray-900">{formattedOrderDate}</p>
                  </div>
                  <div className="space-y-2">
                    <p className="text-xs uppercase tracking-[0.3em] text-gray-400">Quantity</p>
                    <p className="font-semibold text-gray-900">{returnDetail.quantity ?? 1}</p>
                  </div>
                  <div className="space-y-2">
                    <p className="text-xs uppercase tracking-[0.3em] text-gray-400">Amount</p>
                    <p className="font-semibold text-gray-900">₦{(returnDetail.amount ?? 0).toLocaleString()}</p>
                  </div>
                </div>

                <div className="border-t pt-4 text-sm space-y-2">
                  <p className="text-xs uppercase tracking-[0.3em] text-gray-400">Reason</p>
                  <p className="font-semibold text-gray-900">{returnDetail.reason}</p>
                  <p className="text-xs uppercase tracking-[0.3em] text-gray-400">Notes</p>
                  <p className="text-gray-600">{returnDetail.description || '—'}</p>
                  <p className="text-xs uppercase tracking-[0.3em] text-gray-400">Opened</p>
                  <p className="text-gray-600">{returnDetail.opened || '—'}</p>
                  <p className="text-xs uppercase tracking-[0.3em] text-gray-400">Return Action</p>
                  <p className="text-gray-600">{returnDetail.return_action || '—'}</p>
                </div>
              </div>

              <div className="bg-white rounded-lg shadow p-6 space-y-4">
                <h2 className="text-lg font-semibold text-gray-900">Admin Notes</h2>
                <textarea
                  rows={4}
                  value={adminNotes}
                  onChange={(event) => setAdminNotes(event.target.value)}
                  className="w-full border border-gray-200 rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-[#105E53]"
                  placeholder="Add internal notes for this return request"
                />
                <button
                  type="button"
                  onClick={handleUpdateNotes}
                  disabled={saving}
                  className={`px-4 py-2 bg-[#105E53] text-white text-xs uppercase tracking-[0.3em] rounded-sm hover:bg-[#0c4c45] transition ${saving ? 'opacity-70 cursor-not-allowed' : ''}`}
                >
                  Save Notes
                </button>
              </div>
            </div>

            <div className="space-y-6">
              <div className="bg-white rounded-lg shadow p-6 space-y-4">
                <h2 className="text-lg font-semibold text-gray-900">Update Status</h2>
                <label className="text-xs uppercase tracking-[0.3em] text-gray-400">Status</label>
                <select
                  value={status}
                  onChange={(event) => setStatus(event.target.value as ReturnStatus)}
                  className="w-full border border-gray-200 rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-[#105E53]"
                >
                  {STATUS_OPTIONS.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>

                <div className="space-y-2">
                  <label className="text-xs uppercase tracking-[0.3em] text-gray-400">Rejection Reason</label>
                  <input
                    type="text"
                    value={rejectionReason}
                    onChange={(event) => setRejectionReason(event.target.value)}
                    className="w-full border border-gray-200 rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-[#105E53]"
                  />
                  <p className="text-xs text-gray-400">Only required when status is set to rejected.</p>
                </div>

                <div className="space-y-2">
                  <label className="text-xs uppercase tracking-[0.3em] text-gray-400">Refund Amount</label>
                  <input
                    type="number"
                    value={refundAmount}
                    onChange={(event) => setRefundAmount(event.target.value)}
                    disabled={status !== 'refunded'}
                    className={`w-full border border-gray-200 rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-[#105E53] ${status !== 'refunded' ? 'bg-gray-50 text-gray-400 cursor-not-allowed' : ''}`}
                  />
                  <p className="text-xs text-gray-400">Use only when issuing a refund (status: refunded).</p>
                </div>

                <div className="space-y-2">
                  <label className="text-xs uppercase tracking-[0.3em] text-gray-400">Refund Method</label>
                  <input
                    type="text"
                    value={refundMethod}
                    onChange={(event) => setRefundMethod(event.target.value)}
                    disabled={status !== 'refunded'}
                    className={`w-full border border-gray-200 rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-[#105E53] ${status !== 'refunded' ? 'bg-gray-50 text-gray-400 cursor-not-allowed' : ''}`}
                  />
                  <p className="text-xs text-gray-400">Example: Paystack refund, Bank transfer.</p>
                </div>

                <button
                  type="button"
                  onClick={handleUpdateStatus}
                  disabled={saving}
                  className={`w-full px-4 py-2 bg-[#105E53] text-white text-xs uppercase tracking-[0.3em] rounded-sm hover:bg-[#0c4c45] transition ${saving ? 'opacity-70 cursor-not-allowed' : ''}`}
                >
                  Update Status
                </button>
              </div>
            </div>
          </div>
        ) : (
          <div className="bg-white rounded-lg shadow p-10 text-center text-gray-500">
            Return not found.
          </div>
        )}
      </main>
    </div>
  );
}
