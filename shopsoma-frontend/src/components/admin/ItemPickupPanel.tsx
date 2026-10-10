/**
 * Per-item made-to-order readiness + pickup scheduling for the admin order page.
 *
 * Each made-to-order item has its own VendorPickup, so a ready item can be
 * scheduled and collected independently of other vendors in the same order.
 */
import { useState } from 'react';
import { CheckCircle2, Clock3 } from 'lucide-react';
import MadeToOrderReadinessBadge, { MadeToOrderTag, ReadyToWearTag } from '../orders/MadeToOrderReadinessBadge';
import { formatReadyAt } from '../../utils/madeToOrderReadiness';
import { formatProductionDuration, formatWorkingDaysLeft } from '../../utils/productionTracking';
import { updatePickupStatus, adminMarkItemReady } from '../../services/adminOrderService';
import type { OrderDetail, OrderItemDetail, PickupStatusUpdate } from '../../services/adminOrderService';

interface ItemPickupPanelProps {
  orderId: string;
  item: OrderItemDetail;
  onUpdated: (order: OrderDetail) => void;
  onSuccess: (message: string) => void;
  onError: (message: string) => void;
}

const toLocalInputValue = (value?: string | null): string => {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  const offsetMs = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offsetMs).toISOString().slice(0, 16);
};

const toIso = (value: string): string | undefined => {
  if (!value) return undefined;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? undefined : date.toISOString();
};

const errorDetail = (err: unknown, fallback: string): string => {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  return typeof detail === 'string' && detail ? detail : fallback;
};

const WORKING_DAYS_TONE_CLASSES: Record<
  'completed' | 'normal' | 'due-soon' | 'overdue' | 'unavailable',
  string
> = {
  completed: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  normal: 'bg-teal-50 text-teal-700 border-teal-200',
  'due-soon': 'bg-amber-50 text-amber-800 border-amber-200',
  overdue: 'bg-rose-50 text-rose-700 border-rose-200',
  unavailable: 'bg-gray-100 text-gray-600 border-gray-200',
};

export default function ItemPickupPanel({ orderId, item, onUpdated, onSuccess, onError }: ItemPickupPanelProps) {
  const pickup = item.pickup ?? null;
  const isMto = Boolean(
    item.made_to_order ||
    item.order_type === 'made_to_order' ||
    item.order_type === 'custom'
  );
  const state = item.readiness_state ?? (isMto ? 'being_prepared' : (item.ready_for_pickup_at ? 'ready_for_pickup' : null));
  const isReady = isMto
    ? (state === 'ready_for_pickup' || state === 'pickup_scheduled' || state === 'picked_up')
    : Boolean(item.ready_for_pickup_at || state === 'ready_for_pickup' || state === 'pickup_scheduled' || state === 'picked_up');
  const canSchedule = !!pickup && isReady && state !== 'picked_up' && state !== 'cancelled';

  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [markingReady, setMarkingReady] = useState(false);
  const [form, setForm] = useState({
    pickup_window_start: '',
    pickup_window_end: '',
    courier_name: '',
    rider_id: '',
    logistics_partner: '',
    tracking_number: '',
    admin_notes: '',
  });

  const handleMarkReady = async () => {
    try {
      setMarkingReady(true);
      const updated = await adminMarkItemReady(orderId, item.id);
      onUpdated(updated);
      onSuccess(`Marked ${item.product_title} as ready for pickup. You can now schedule pickup.`);
    } catch (err) {
      console.error('Failed to mark item ready:', err);
      onError(errorDetail(err, 'Failed to mark item ready for pickup'));
    } finally {
      setMarkingReady(false);
    }
  };

  const openEditor = () => {
    setForm({
      pickup_window_start: toLocalInputValue(pickup?.pickup_window_start),
      pickup_window_end: toLocalInputValue(pickup?.pickup_window_end),
      courier_name: pickup?.courier_name || '',
      rider_id: pickup?.rider_id || '',
      logistics_partner: pickup?.logistics_partner || '',
      tracking_number: pickup?.tracking_number || '',
      admin_notes: '',
    });
    setEditing(true);
  };

  const submit = async (data: PickupStatusUpdate, successMessage: string) => {
    if (!pickup) return;
    try {
      setSaving(true);
      const updated = await updatePickupStatus(orderId, pickup.id, data);
      onUpdated(updated);
      onSuccess(successMessage);
      setEditing(false);
    } catch (err) {
      console.error('Failed to update item pickup:', err);
      onError(errorDetail(err, 'Failed to update pickup for this item'));
    } finally {
      setSaving(false);
    }
  };

  const handleSave = async () => {
    const start = toIso(form.pickup_window_start);
    const end = toIso(form.pickup_window_end);
    if (!start || !end) {
      onError('Please select both start and end times for the pickup window');
      return;
    }
    if (new Date(end) <= new Date(start)) {
      onError('Pickup window end must be after the start');
      return;
    }
    await submit(
      {
        pickup_window_start: start,
        pickup_window_end: end,
        courier_name: form.courier_name || undefined,
        rider_id: form.rider_id || undefined,
        logistics_partner: form.logistics_partner || undefined,
        tracking_number: form.tracking_number || undefined,
        admin_notes: form.admin_notes || undefined,
      },
      `Pickup scheduled for ${item.vendor.business_name} — ${item.product_title}`
    );
  };

  const isCompleted =
    item.is_production_completed ||
    !!item.ready_for_pickup_at ||
    state === 'ready_for_pickup' ||
    state === 'pickup_scheduled' ||
    state === 'picked_up';

  const duration = formatProductionDuration(
    item.production_duration,
    item.estimated_production_days ?? item.pickup?.estimated_production_days
  );

  const countdown = formatWorkingDaysLeft({
    ...item,
    is_production_completed: isCompleted,
  });

  const dueDate = formatReadyAt(item.production_due_date);
  const readyAt = formatReadyAt(item.ready_for_pickup_at);
  const windowStart = formatReadyAt(pickup?.pickup_window_start || pickup?.scheduled_pickup_date);
  const windowEnd = formatReadyAt(pickup?.pickup_window_end);
  const pickedUpAt = formatReadyAt(pickup?.actual_pickup_date);

  return (
    <div
      className="mt-3 rounded-lg border border-gray-200 bg-gray-50 p-3 space-y-2"
      data-testid={`item-pickup-panel-${item.id}`}
    >
      {isMto ? (
        <div className="flex flex-wrap items-center gap-2">
          <MadeToOrderTag />
          <MadeToOrderReadinessBadge state={state ?? 'being_prepared'} />
          {duration ? (
            <span
              className="inline-flex items-center rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-700 border border-slate-200"
              data-testid="mto-duration"
            >
              Duration: {duration}
            </span>
          ) : (
            <span
              className="inline-flex items-center rounded-full bg-gray-100 px-2.5 py-1 text-xs font-medium text-gray-500 border border-gray-200"
              data-testid="mto-duration"
            >
              Duration: Not specified
            </span>
          )}
          <span
            className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold border ${WORKING_DAYS_TONE_CLASSES[countdown.tone]}`}
            data-testid="mto-countdown"
          >
            {countdown.text}
          </span>
        </div>
      ) : (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs font-semibold text-gray-700">Individual Pickup:</span>
          {isReady ? (
            <span
              className="inline-flex items-center gap-1.5 rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-xs font-semibold text-emerald-700"
            >
              <CheckCircle2 className="h-3.5 w-3.5" />
              Ready for pickup
            </span>
          ) : (
            <span
              className="inline-flex items-center gap-1.5 rounded-full border border-amber-200 bg-amber-50 px-2.5 py-1 text-xs font-semibold text-amber-800"
            >
              <Clock3 className="h-3.5 w-3.5" />
              Awaiting vendor confirmation
            </span>
          )}
        </div>
      )}

      {isMto ? (
        readyAt ? (
          <p className="text-xs text-gray-600">Marked ready: {readyAt}</p>
        ) : (
          <>
            {dueDate && (
              <p className="text-xs text-gray-500">
                Estimated completion: {dueDate}
              </p>
            )}
            {state === 'being_prepared' && (
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-xs text-gray-500">
                  Waiting for {item.vendor.business_name} to mark this item ready. Pickup can be scheduled once it is ready.
                </p>
                <button
                  type="button"
                  onClick={handleMarkReady}
                  disabled={markingReady || saving}
                  className="px-2.5 py-1 text-xs font-medium rounded border border-[#105E53] text-[#105E53] bg-white hover:bg-[#f1f8f6] disabled:opacity-50"
                  data-testid={`mark-ready-${item.id}`}
                >
                  {markingReady ? 'Marking ready...' : 'Mark Ready (Admin)'}
                </button>
              </div>
            )}
          </>
        )
      ) : (
        !isReady && (
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-xs text-gray-500">
              Awaiting vendor confirmation. Pickup can be scheduled once marked ready.
            </p>
            <button
              type="button"
              onClick={handleMarkReady}
              disabled={markingReady || saving}
              className="px-2.5 py-1 text-xs font-medium rounded border border-[#105E53] text-[#105E53] bg-white hover:bg-[#f1f8f6] disabled:opacity-50"
              data-testid={`mark-ready-${item.id}`}
            >
              {markingReady ? 'Marking ready...' : 'Mark Ready (Admin)'}
            </button>
          </div>
        )
      )}

      {windowStart && (state === 'pickup_scheduled' || state === 'picked_up') && (
        <p className="text-xs text-gray-600">
          Pickup window: {windowStart}
          {windowEnd ? ` – ${windowEnd}` : ''}
          {pickup?.courier_name ? ` · ${pickup.courier_name}` : ''}
          {pickup?.rider_id ? ` · Rider ${pickup.rider_id}` : ''}
        </p>
      )}
      {pickup?.tracking_number && (
        <p className="text-xs text-gray-600">Tracking: {pickup.tracking_number}</p>
      )}
      {state === 'picked_up' && pickedUpAt && (
        <p className="text-xs text-gray-600">Picked up: {pickedUpAt}</p>
      )}

      {canSchedule && !editing && (
        <div className="flex flex-wrap gap-2 pt-1">
          <button
            type="button"
            onClick={openEditor}
            disabled={saving}
            className="px-3 py-1.5 text-xs font-semibold rounded-lg bg-[#105E53] text-white hover:bg-[#0d4a41] disabled:opacity-50"
          >
            {state === 'pickup_scheduled' ? 'Edit pickup' : 'Schedule pickup'}
          </button>
          {state === 'pickup_scheduled' && (
            <button
              type="button"
              onClick={() =>
                submit(
                  { pickup_status: 'in_transit' },
                  `${item.vendor.business_name} — ${item.product_title} marked as picked up`
                )
              }
              disabled={saving}
              className="px-3 py-1.5 text-xs font-semibold rounded-lg border border-gray-300 bg-white text-gray-700 hover:bg-gray-100 disabled:opacity-50"
            >
              {saving ? 'Saving...' : 'Mark picked up'}
            </button>
          )}
        </div>
      )}

      {canSchedule && editing && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
          <label className="text-xs font-medium text-gray-700">
            Pickup window start *
            <input
              type="datetime-local"
              value={form.pickup_window_start}
              onChange={(e) => setForm({ ...form, pickup_window_start: e.target.value })}
              className="mt-1 w-full px-2 py-1.5 border border-gray-300 rounded-lg text-sm"
            />
          </label>
          <label className="text-xs font-medium text-gray-700">
            Pickup window end *
            <input
              type="datetime-local"
              value={form.pickup_window_end}
              onChange={(e) => setForm({ ...form, pickup_window_end: e.target.value })}
              className="mt-1 w-full px-2 py-1.5 border border-gray-300 rounded-lg text-sm"
            />
          </label>
          <label className="text-xs font-medium text-gray-700">
            Courier name
            <input
              type="text"
              value={form.courier_name}
              onChange={(e) => setForm({ ...form, courier_name: e.target.value })}
              className="mt-1 w-full px-2 py-1.5 border border-gray-300 rounded-lg text-sm"
            />
          </label>
          <label className="text-xs font-medium text-gray-700">
            Rider ID
            <input
              type="text"
              value={form.rider_id}
              onChange={(e) => setForm({ ...form, rider_id: e.target.value })}
              className="mt-1 w-full px-2 py-1.5 border border-gray-300 rounded-lg text-sm"
            />
          </label>
          <label className="text-xs font-medium text-gray-700">
            Logistics partner
            <input
              type="text"
              value={form.logistics_partner}
              onChange={(e) => setForm({ ...form, logistics_partner: e.target.value })}
              className="mt-1 w-full px-2 py-1.5 border border-gray-300 rounded-lg text-sm"
            />
          </label>
          <label className="text-xs font-medium text-gray-700">
            Tracking number
            <input
              type="text"
              value={form.tracking_number}
              onChange={(e) => setForm({ ...form, tracking_number: e.target.value })}
              className="mt-1 w-full px-2 py-1.5 border border-gray-300 rounded-lg text-sm"
            />
          </label>
          <label className="text-xs font-medium text-gray-700 sm:col-span-2">
            Notes
            <textarea
              value={form.admin_notes}
              onChange={(e) => setForm({ ...form, admin_notes: e.target.value })}
              rows={2}
              className="mt-1 w-full px-2 py-1.5 border border-gray-300 rounded-lg text-sm"
            />
          </label>
          <div className="flex gap-2 sm:col-span-2">
            <button
              type="button"
              onClick={handleSave}
              disabled={saving}
              className="px-3 py-1.5 text-xs font-semibold rounded-lg bg-[#105E53] text-white hover:bg-[#0d4a41] disabled:opacity-50"
            >
              {saving ? 'Saving...' : 'Save pickup'}
            </button>
            <button
              type="button"
              onClick={() => setEditing(false)}
              disabled={saving}
              className="px-3 py-1.5 text-xs font-semibold rounded-lg border border-gray-300 bg-white text-gray-700 hover:bg-gray-100"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
