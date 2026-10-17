import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import api from '../../services/api';
import { ROUTES } from '../../config/constants';
import { createDhlBooking, getDhlLabel, getOrderDetail, recordDhlHandoff, refreshDhlTracking } from '../../services/adminOrderService';
import type { OrderDetail } from '../../services/adminOrderService';

const emptyHandoff = { occurred_at: '', counterparty: '', evidence_ref: '', evidence_sha256: '' };
type Handoff = typeof emptyHandoff;
type Confirmation = { operation: Operation; target: string; draft: Handoff };
type Operation = 'book' | 'handoff' | 'tracking';

const unresolved = new Set(['in_progress', 'required', 'expired_claim_requires_recovery', 'inconsistent']);
const blockerCopy: Record<string, string> = {
  order_cancelled: 'Order cancelled',
  package_not_ready: 'Package is not ready',
  custody_handed_off: 'Package has left hub custody',
  active_seal_missing: 'Active seal unavailable',
  active_intent_missing: 'Shipment intent unavailable',
  selected_dhl_quote_missing: 'Selected DHL quote unavailable',
  active_booking_exists: 'Shipment attempt already exists',
  reconciliation_required: 'Reconciliation required',
  expired_claim_requires_recovery: 'Expired attempt requires authorized recovery',
  inconsistent_persisted_state: 'Shipment records require review',
};

const btnBase = 'inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium transition shadow-xs disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-offset-1';
const btnPrimary = `${btnBase} bg-[#105E53] hover:bg-[#0d4a41] text-white focus:ring-[#105E53]`;
const btnSecondary = `${btnBase} bg-white hover:bg-gray-50 text-gray-700 border border-gray-300 focus:ring-gray-300`;
const btnAmber = `${btnBase} bg-gradient-to-r from-amber-400 to-amber-500 hover:from-amber-500 hover:to-amber-600 text-amber-950 font-semibold border border-amber-400 shadow-sm focus:ring-amber-400`;

async function computeSha256(text: string): Promise<string> {
  try {
    const encoder = new TextEncoder();
    const data = encoder.encode(text);
    const hashBuffer = await window.crypto.subtle.digest('SHA-256', data);
    const hashArray = Array.from(new Uint8Array(hashBuffer));
    return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
  } catch {
    return '';
  }
}

function getLocalNowString(): string {
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}T${pad(now.getHours())}:${pad(now.getMinutes())}`;
}

export default function DhlShipmentOperations({ order, onOrderChange, disabled = false }: {
  order: OrderDetail; onOrderChange: (order: OrderDetail) => void; disabled?: boolean;
}) {
  const facts = order.dhl_operations;
  const storageKey = `shopsoma:dhl:unresolved:${order.id}`;
  const [held, setHeld] = useState(() => {
    try { return localStorage.getItem(storageKey) !== null; } catch { return true; }
  });
  useEffect(() => {
    const changed = (event: StorageEvent) => { if (event.key === storageKey && event.newValue !== null) setHeld(true); };
    window.addEventListener('storage', changed);
    return () => window.removeEventListener('storage', changed);
  }, [storageKey]);
  const [packageId, setPackageId] = useState('');
  const [bookingId, setBookingId] = useState('');
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null);
  const [busy, setBusy] = useState(false);
  const running = useRef(false);
  const [message, setMessage] = useState('');
  const [drafts, setDrafts] = useState<Record<string, Handoff>>({});
  const packages = facts?.packages ?? [];
  const ready = packages.filter(p => p.package_state === 'ready');
  const selected = packages.find(p => p.package_id === (packageId || (ready.length === 1 ? ready[0].package_id : '')));
  const bookings = facts?.bookings ?? [];
  const booking = bookings.find(b => b.booking_id === (bookingId || (bookings.length === 1 ? bookings[0].booking_id : '')));
  const cancelled = order.fulfillment_status === 'cancelled';
  const locked = busy || disabled || confirmation !== null;
  const canBook = !!facts && !!selected?.selection_eligible && !!selected.intent_id && !!selected.seal_id && !held && !cancelled;
  const usableBooking = !!booking && booking.classification === 'success' && !unresolved.has(booking.reconciliation_state);

  const draftKey = JSON.stringify([order.id, booking?.booking_id]);
  const handoff = drafts[draftKey] ?? emptyHandoff;
  const setHandoff = (value: Handoff) => setDrafts(previous => ({ ...previous, [draftKey]: value }));
  const trigger = useRef<HTMLElement | null>(null);
  const restoreFocus = useRef(false);
  const heading = useRef<HTMLHeadingElement>(null);
  const status = useRef<HTMLParagraphElement>(null);
  const shipmentSelect = useRef<HTMLSelectElement>(null);
  const handoffSubmit = useRef<HTMLButtonElement>(null);
  const targetFor = (operation: Operation) => JSON.stringify(operation === 'book'
    ? [order.id, selected?.package_id, selected?.package_version, selected?.intent_id, selected?.seal_id]
    : [order.id, booking?.booking_id, booking?.package_id, booking?.package_version, booking?.seal_id]);
  const confirmationValid = !confirmation || (confirmation.target === targetFor(confirmation.operation) &&
    !disabled && !cancelled && !held && (confirmation.operation === 'book' ? canBook :
      usableBooking && (confirmation.operation !== 'handoff' || !booking?.handoff_recorded_at)));
  const closeConfirmation = () => { restoreFocus.current = true; setConfirmation(null); };
  const openConfirmation = (operation: Operation, source: HTMLElement) => {
    trigger.current = source;
    setConfirmation({ operation, target: targetFor(operation), draft: { ...handoff } });
  };
  useLayoutEffect(() => {
    if (!confirmation && restoreFocus.current) {
      restoreFocus.current = false;
      const source = trigger.current;
      if (busy) status.current?.focus();
      else if (source?.isConnected && !source.matches(':disabled')) source.focus();
      else if (shipmentSelect.current && !shipmentSelect.current.disabled) shipmentSelect.current.focus();
      else heading.current?.focus();
    }
  }, [confirmation, busy]);
  useEffect(() => {
    if (confirmation && !confirmationValid) {
      restoreFocus.current = true;
      setConfirmation(null);
      setMessage('Shipment records changed. Review the selected shipment before continuing.');
    }
  }, [confirmation, confirmationValid]);

  async function reload() {
    const fresh = await getOrderDetail(order.id);
    onOrderChange(fresh);
    return fresh;
  }

  async function execute() {
    const op = confirmation?.operation;
    if (!op || !confirmation || !confirmationValid || running.current || disabled) return;
    if ((op === 'book' && !canBook) || (op !== 'book' && (!usableBooking || cancelled || held))) return;
    running.current = true;
    setBusy(true);
    setMessage('');
    closeConfirmation();
    try {
      if (localStorage.getItem(storageKey) !== null) { setHeld(true); return; }
      const idempotency_key = crypto.randomUUID();
      setHeld(true);
      localStorage.setItem(storageKey, '1');
      if (op === 'book' && selected?.intent_id && selected.seal_id) {
        const result = await createDhlBooking(order.id, {
          intent_id: selected.intent_id, package_id: selected.package_id,
          package_version: selected.package_version, seal_id: selected.seal_id, idempotency_key,
        });
        const fresh = await reload();
        const persisted = fresh.dhl_operations?.bookings.find(b => b.booking_id === result.booking_id);
        if (persisted && ((result.result_kind === 'booked' && persisted.classification === 'success') ||
          (result.result_kind === 'failure' && persisted.classification === 'failure')) && !unresolved.has(persisted.reconciliation_state)) {
          localStorage.removeItem(storageKey);
          setHeld(false);
        }
        setBookingId(result.booking_id);
        setMessage(result.result_kind === 'booked' ? 'DHL shipment created. Review the refreshed shipment record.' :
          result.result_kind === 'failure' ? 'DHL shipment was not created. Review the refreshed record before any new attempt.' :
            'Shipment outcome needs review. Do not retry; request authorized reconciliation.');
      } else if (op === 'handoff' && booking) {
        await recordDhlHandoff(order.id, booking.booking_id, {
          ...confirmation.draft, occurred_at: new Date(confirmation.draft.occurred_at).toISOString(),
          counterparty: confirmation.draft.counterparty.trim(), evidence_ref: confirmation.draft.evidence_ref.trim(),
          evidence_sha256: confirmation.draft.evidence_sha256.trim().toLowerCase(), idempotency_key,
        });
        setHandoff({ ...emptyHandoff });
        await reload();
        localStorage.removeItem(storageKey); setHeld(false);
        setMessage('Hub-to-DHL handoff recorded.');
      } else if (op === 'tracking' && booking) {
        await refreshDhlTracking(order.id, { booking_id: booking.booking_id, idempotency_key });
        await reload();
        localStorage.removeItem(storageKey); setHeld(false);
        setMessage('DHL tracking refreshed.');
      }
    } catch {
      setMessage('Operation could not be confirmed. Refresh shipment records and review the outcome before continuing. Do not blindly retry.');
      try { await reload(); } catch { /* Keep existing locks and fixed safe message. */ }
    } finally {
      running.current = false;
      setBusy(false);
    }
  }

  async function downloadLabel() {
    if (!booking?.label_available || running.current) return;
    running.current = true; setBusy(true); setMessage('');
    try {
      const blob = await getDhlLabel(order.id, booking.booking_id);
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url; link.download = `dhl-label-${booking.booking_id}.pdf`;
      document.body.appendChild(link); link.click(); link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      setMessage('DHL label downloaded.');
    } catch { setMessage('DHL label could not be downloaded. Refresh the shipment record and try again.'); }
    finally { running.current = false; setBusy(false); }
  }

  async function prepareHubPackage() {
    if (running.current || locked || cancelled) return;
    running.current = true; setBusy(true); setMessage('');
    try {
      const response = await api.post<OrderDetail>(`/admin/orders/${order.id}/dhl/prepare-package`);
      onOrderChange(response.data);
      const firstReady = response.data.dhl_operations?.packages.find(p => p.package_state === 'ready');
      if (firstReady) setPackageId(firstReady.package_id);
      setMessage('Hub package, seal, shipment intent, and selected DHL quote prepared.');
    } catch {
      setMessage('Hub package could not be prepared. Ensure the order is paid and has valid items.');
    } finally {
      running.current = false; setBusy(false);
    }
  }

  const handleAutoFillHandoff = async () => {
    const occurred_at = getLocalNowString();
    const counterparty = 'DHL Express Courier';
    const evidence_ref = `WAYBILL-RECEIPT-${booking?.tracking_number || order.order_number || order.id.slice(0, 8).toUpperCase()}`;
    const evidence_sha256 = await computeSha256(evidence_ref);
    setHandoff({
      occurred_at,
      counterparty,
      evidence_ref,
      evidence_sha256,
    });
  };

  const handleGenerateSha256 = async () => {
    const target = handoff.evidence_ref.trim() || `WAYBILL-RECEIPT-${booking?.tracking_number || order.order_number || order.id.slice(0, 8).toUpperCase()}`;
    const hash = await computeSha256(target);
    setHandoff({
      ...handoff,
      evidence_ref: handoff.evidence_ref || target,
      evidence_sha256: hash,
    });
  };

  return (
    <section className="bg-white rounded-xl border border-gray-200 shadow-sm p-5 sm:p-7 space-y-6" aria-labelledby="dhl-operations-title">
      {/* Top Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-gray-100 pb-4">
        <div>
          <h2 ref={heading} tabIndex={-1} id="dhl-operations-title" className="text-lg sm:text-xl font-bold text-gray-900 flex items-center gap-2">
            <span aria-hidden="true" className="inline-flex items-center justify-center w-7 h-7 rounded-md bg-[#FFCC00] text-[#D40511] font-black text-xs shadow-2xs border border-amber-300">
              DHL
            </span>
            DHL Shipment Operations
          </h2>
          <p className="text-xs text-gray-500 mt-1">
            DHL pickup booking is unavailable. Record handoff only after actual collection from the ShopSoma hub.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-amber-50 text-red-900 border border-amber-300">
            <span className="w-2 h-2 rounded-full bg-amber-500" />
            DHL Express · MyDHL API
          </span>
        </div>
      </div>

      {!facts ? (
        <div role="status" className="p-4 rounded-lg bg-gray-50 text-gray-600 text-sm border border-gray-200">
          Shipment operations are unavailable until backend shipment facts can be loaded.
        </div>
      ) : (
        <>
          {/* Hub Package Preparation / Selection Card */}
          <div className="rounded-xl border border-gray-200/80 bg-gray-50/60 p-4 sm:p-5 space-y-4">
            <div className="space-y-1.5">
              <label htmlFor="dhl-ready-hub-package" className="block text-xs font-semibold text-gray-700 uppercase tracking-wider">
                Ready hub package
              </label>
              <select
                id="dhl-ready-hub-package"
                className="w-full rounded-lg border border-gray-300 bg-white px-3.5 py-2.5 text-sm text-gray-900 shadow-2xs focus:border-[#105E53] focus:ring-2 focus:ring-[#105E53] transition"
                aria-label="Ready hub package"
                value={selected?.package_id ?? ''}
                disabled={locked}
                onChange={e => setPackageId(e.target.value)}
              >
                <option value="">Select ready package</option>
                {ready.map(p => (
                  <option key={p.package_id} value={p.package_id}>
                    {p.package_id} · version {p.package_version} · hub {p.origin_hub_id}
                  </option>
                ))}
              </select>
            </div>

            {ready.length === 0 && (
              <div className="flex flex-wrap items-center justify-between gap-3 p-3.5 bg-amber-50/60 border border-amber-200 rounded-lg">
                <p className="text-xs text-amber-900 font-medium">No ready hub packages.</p>
                {!bookings.length && !cancelled && order.payment_status === 'paid' && (
                  <button
                    type="button"
                    className="px-3.5 py-1.5 text-xs font-semibold rounded-md bg-amber-400 text-red-950 hover:bg-amber-300 disabled:opacity-50 transition shadow-2xs"
                    disabled={locked}
                    onClick={prepareHubPackage}
                  >
                    Prepare Hub Package for DHL
                  </button>
                )}
              </div>
            )}

            {selected && (
              <div className="flex flex-wrap items-center gap-2 pt-1 text-xs text-gray-600">
                <span className="font-medium text-gray-700">Origin:</span> ShopSoma hub {selected.origin_hub_id}
                <span className="text-gray-300">|</span>
                <span className="font-medium text-gray-700">Package version:</span> {selected.package_version}
              </div>
            )}

            {selected?.selection_blockers.map(code => (
              <div key={code} className="p-3 bg-red-50 border border-red-200 text-red-700 text-xs rounded-lg flex items-center gap-2">
                <span>⚠️</span>
                <span>{blockerCopy[code] ?? 'Shipment records require review'}</span>
              </div>
            ))}

            {held && (
              <div role="alert" className="p-3 bg-red-50 border border-red-200 text-red-800 text-xs rounded-lg">
                An unresolved local shipment command blocks new mutations, including after reload. Request authorized outcome review; an empty record does not prove no shipment was created.
              </div>
            )}

            <div>
              <button
                className={canBook ? btnAmber : btnSecondary}
                disabled={locked || !canBook}
                onClick={e => openConfirmation('book', e.currentTarget)}
              >
                Create DHL shipment
              </button>
            </div>
          </div>

          {/* Shipment Records Card */}
          <div className="rounded-xl border border-gray-200/90 bg-white p-4 sm:p-5 space-y-4">
            <div className="space-y-1.5">
              <label htmlFor="dhl-shipment-record" className="block text-xs font-semibold text-gray-700 uppercase tracking-wider">
                Shipment record
              </label>
              <select
                id="dhl-shipment-record"
                className="w-full rounded-lg border border-gray-300 bg-white px-3.5 py-2.5 text-sm text-gray-900 shadow-2xs focus:border-[#105E53] focus:ring-2 focus:ring-[#105E53] transition"
                aria-label="Shipment record"
                ref={shipmentSelect}
                value={booking?.booking_id ?? ''}
                disabled={locked}
                onChange={e => setBookingId(e.target.value)}
              >
                <option value="">Select shipment record</option>
                {bookings.map(b => (
                  <option key={b.booking_id} value={b.booking_id}>
                    {b.booking_id} · {b.classification}
                  </option>
                ))}
              </select>
            </div>

            {!bookings.length && (
              <p className="text-xs text-gray-500 py-1">No recorded DHL shipments.</p>
            )}

            {booking && (
              <div className="space-y-4 pt-2">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 p-3.5 bg-gray-50 rounded-lg border border-gray-200/80 text-xs text-gray-700">
                  <div>
                    <span className="font-semibold text-gray-900">Package:</span> {booking.package_id} · v{booking.package_version}
                  </div>
                  <div>
                    <span className="font-semibold text-gray-900">Hub:</span> {booking.origin_hub_id}
                  </div>
                  <div>
                    <span className="font-semibold text-gray-900">Shipment status:</span>{' '}
                    <span className="capitalize font-medium text-emerald-800 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
                      {booking.outbound_state}
                    </span>
                  </div>
                  <div>
                    <span className="font-semibold text-gray-900">Outcome:</span>{' '}
                    <span className="capitalize font-medium text-blue-800 bg-blue-50 px-2 py-0.5 rounded border border-blue-200">
                      {booking.classification}
                    </span>
                  </div>
                  {booking.tracking_number && (
                    <div className="sm:col-span-2 flex items-center gap-2 pt-1 border-t border-gray-200/70">
                      <span className="font-semibold text-gray-900">Tracking number:</span>
                      <span className="font-mono font-bold text-sm text-[#105E53] bg-emerald-50/80 px-2.5 py-1 rounded border border-emerald-300">
                        {booking.tracking_number}
                      </span>
                    </div>
                  )}
                </div>

                {unresolved.has(booking.reconciliation_state) && (
                  <div role="alert" className="p-3 bg-amber-50 border border-amber-300 text-amber-900 text-xs rounded-lg">
                    This attempt requires review ({booking.reconciliation_state.replaceAll('_', ' ')}). Booking retries are unavailable.
                  </div>
                )}

                {/* Primary Action Buttons */}
                <div className="flex flex-wrap items-center gap-2.5">
                  <button
                    className={btnPrimary}
                    disabled={locked || !booking.label_available}
                    onClick={downloadLabel}
                  >
                    <span aria-hidden="true">📄</span>
                    Download DHL label
                  </button>
                  <button
                    className={btnSecondary}
                    disabled={locked || !usableBooking || cancelled || held}
                    onClick={e => openConfirmation('tracking', e.currentTarget)}
                  >
                    <span aria-hidden="true">🔄</span>
                    Refresh DHL tracking
                  </button>
                  {booking.tracking_number && (
                    <a
                      href={`${ROUTES.ORDER_MAP_TRACKING.replace(':orderId', order.id)}?from=admin`}
                      className={btnAmber}
                    >
                      <span aria-hidden="true">🗺️</span>
                      Open Live Tracking Map
                    </a>
                  )}
                </div>

                {/* Hub Custody Handoff Section */}
                {booking.handoff_recorded_at ? (
                  <div className="p-4 rounded-xl border border-emerald-300 bg-emerald-50/80 text-emerald-900 flex items-center gap-3">
                    <span className="text-xl">✅</span>
                    <div>
                      <p className="font-semibold text-sm">Handoff recorded: {booking.handoff_recorded_at}</p>
                      <p className="text-xs text-emerald-700 mt-0.5">Package custody was transferred from the Shopsoma hub to the courier.</p>
                    </div>
                  </div>
                ) : (
                  <form
                    className="space-y-4 rounded-xl border border-amber-300/80 bg-gradient-to-br from-amber-50/40 via-white to-gray-50/40 p-5 sm:p-6"
                    onSubmit={e => {
                      e.preventDefault();
                      if (locked || !usableBooking || cancelled || held || booking.handoff_recorded_at) return;
                      if (!e.currentTarget.reportValidity()) return;
                      const ref = handoff.evidence_ref.trim();
                      if (ref.includes('://') || ref.startsWith('/') || ref.includes('..') || !handoff.counterparty.trim() || !ref) {
                        setMessage('Enter a private evidence reference and counterparty. URLs and absolute paths are not accepted.');
                        return;
                      }
                      if (handoffSubmit.current) openConfirmation('handoff', handoffSubmit.current);
                    }}
                  >
                    <fieldset disabled={locked || !usableBooking || cancelled || held} className="space-y-4">
                      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-amber-200/60 pb-3">
                        <div>
                          <legend className="text-sm sm:text-base font-bold text-gray-900">
                            Record hub-to-DHL handoff for {booking.booking_id}
                          </legend>
                          <p className="text-xs text-gray-600 mt-0.5">
                            Handoff details apply only to the selected shipment. Unsaved details are kept only while this order is open.
                          </p>
                        </div>
                        <button
                          type="button"
                          onClick={handleAutoFillHandoff}
                          className="px-3 py-1.5 text-xs font-semibold rounded-md border border-amber-300 bg-amber-100 text-amber-950 hover:bg-amber-200 transition shadow-2xs"
                        >
                          ⚡ Auto-Fill Sample Evidence
                        </button>
                      </div>

                      {/* 2-Column Responsive Form Fields */}
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-1">
                        {/* 1. Collection Time */}
                        <div className="space-y-1.5">
                          <div className="flex items-center justify-between">
                            <label htmlFor="dhl-handoff-time" className="block text-xs font-semibold text-gray-700 uppercase tracking-wider">
                              Collection time (your local time)
                            </label>
                            <button
                              type="button"
                              onClick={() => setHandoff({ ...handoff, occurred_at: getLocalNowString() })}
                              className="text-xs font-medium text-[#105E53] hover:underline cursor-pointer"
                            >
                              Set to Now
                            </button>
                          </div>
                          <input
                            id="dhl-handoff-time"
                            aria-label="Collection time (your local time)"
                            className="w-full rounded-lg border border-gray-300 bg-white px-3.5 py-2.5 text-sm text-gray-900 shadow-2xs focus:border-[#105E53] focus:ring-2 focus:ring-[#105E53] transition"
                            required
                            type="datetime-local"
                            value={handoff.occurred_at}
                            onChange={e => setHandoff({ ...handoff, occurred_at: e.target.value })}
                          />
                          <p className="text-[11px] text-gray-500">When the DHL courier picked up the package at the hub.</p>
                        </div>

                        {/* 2. Counterparty */}
                        <div className="space-y-1.5">
                          <div className="flex items-center justify-between">
                            <label htmlFor="dhl-handoff-counterparty" className="block text-xs font-semibold text-gray-700 uppercase tracking-wider">
                              Counterparty
                            </label>
                            <button
                              type="button"
                              onClick={() => setHandoff({ ...handoff, counterparty: 'DHL Express Courier' })}
                              className="text-xs font-medium text-[#105E53] hover:underline cursor-pointer"
                            >
                              + DHL Courier
                            </button>
                          </div>
                          <input
                            id="dhl-handoff-counterparty"
                            aria-label="Counterparty"
                            className="w-full rounded-lg border border-gray-300 bg-white px-3.5 py-2.5 text-sm text-gray-900 shadow-2xs focus:border-[#105E53] focus:ring-2 focus:ring-[#105E53] transition"
                            required
                            maxLength={120}
                            autoComplete="off"
                            placeholder="e.g. DHL Courier - Tunde (Driver #429)"
                            value={handoff.counterparty}
                            onChange={e => setHandoff({ ...handoff, counterparty: e.target.value })}
                          />
                          <p className="text-[11px] text-gray-500">Name or badge ID of the courier driver collecting the package.</p>
                        </div>

                        {/* 3. Private evidence reference */}
                        <div className="space-y-1.5">
                          <div className="flex items-center justify-between">
                            <label htmlFor="dhl-handoff-evidence-ref" className="block text-xs font-semibold text-gray-700 uppercase tracking-wider">
                              Private evidence reference
                            </label>
                            <button
                              type="button"
                              onClick={() => {
                                const ref = `WAYBILL-RECEIPT-${booking.tracking_number || order.order_number || order.id.slice(0, 8).toUpperCase()}`;
                                setHandoff({ ...handoff, evidence_ref: ref });
                              }}
                              className="text-xs font-medium text-[#105E53] hover:underline cursor-pointer"
                            >
                              Use Waybill #
                            </button>
                          </div>
                          <input
                            id="dhl-handoff-evidence-ref"
                            aria-label="Private evidence reference"
                            className="w-full rounded-lg border border-gray-300 bg-white px-3.5 py-2.5 text-sm text-gray-900 shadow-2xs focus:border-[#105E53] focus:ring-2 focus:ring-[#105E53] transition"
                            required
                            maxLength={200}
                            autoComplete="off"
                            placeholder="e.g. WAYBILL-RECEIPT-8501906011"
                            value={handoff.evidence_ref}
                            onChange={e => setHandoff({ ...handoff, evidence_ref: e.target.value })}
                          />
                          <p className="text-[11px] text-gray-500">Internal handover paper slip ID or log tag (no URLs or paths).</p>
                        </div>

                        {/* 4. Evidence SHA-256 */}
                        <div className="space-y-1.5">
                          <div className="flex items-center justify-between">
                            <label htmlFor="dhl-handoff-sha256" className="block text-xs font-semibold text-gray-700 uppercase tracking-wider">
                              Evidence SHA-256
                            </label>
                            <button
                              type="button"
                              onClick={handleGenerateSha256}
                              className="text-xs font-medium text-[#105E53] hover:underline cursor-pointer"
                            >
                              ⚡ Compute Hash
                            </button>
                          </div>
                          <input
                            id="dhl-handoff-sha256"
                            aria-label="Evidence SHA-256"
                            className="w-full rounded-lg border border-gray-300 bg-white px-3.5 py-2.5 text-sm font-mono text-gray-900 shadow-2xs focus:border-[#105E53] focus:ring-2 focus:ring-[#105E53] transition"
                            required
                            pattern="[a-fA-F0-9]{64}"
                            maxLength={64}
                            autoComplete="off"
                            placeholder="64-character lowercase hex digest"
                            value={handoff.evidence_sha256}
                            onChange={e => setHandoff({ ...handoff, evidence_sha256: e.target.value })}
                          />
                          <p className="text-[11px] text-gray-500">Cryptographic audit hash verifying the handover proof document.</p>
                        </div>
                      </div>

                      <div className="pt-2 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                        <p className="text-xs text-gray-500 max-w-lg leading-relaxed">
                          Requires verified DHL collection tracking and valid hub custody. Evidence is sent privately and is not saved in browser storage.
                        </p>
                        <button ref={handoffSubmit} className={btnPrimary} type="submit">
                          Record DHL handoff
                        </button>
                      </div>
                    </fieldset>
                  </form>
                )}
              </div>
            )}
          </div>
        </>
      )}

      {/* Bottom Footer Actions & Status Message */}
      <div className="flex flex-wrap items-center justify-between gap-3 pt-3 border-t border-gray-100">
        <button
          className={btnSecondary}
          disabled={locked}
          onClick={async () => {
            if (running.current) return;
            running.current = true;
            setBusy(true);
            try {
              await reload();
              setMessage('Shipment records refreshed.');
            } catch {
              setMessage('Shipment records could not be refreshed. Existing safety restrictions remain.');
            } finally {
              running.current = false;
              setBusy(false);
            }
          }}
        >
          <span aria-hidden="true" className={busy ? 'animate-spin' : ''}>🔄</span>
          Reload shipment records
        </button>

        <p
          ref={status}
          tabIndex={-1}
          role="status"
          className={`text-sm font-medium ${
            message.includes('recorded') || message.includes('created') || message.includes('downloaded')
              ? 'text-emerald-700'
              : message.includes('could not') || message.includes('require') || message.includes('blocked')
              ? 'text-red-700'
              : 'text-gray-600'
          }`}
        >
          {busy ? 'DHL operation in progress…' : message}
        </p>
      </div>

      {confirmation && (
        <DhlConfirmation
          onCancel={closeConfirmation}
          onConfirm={execute}
          operation={confirmation.operation}
          description={
            confirmation.operation === 'book'
              ? `Create a shipment from hub ${selected?.origin_hub_id} for package ${selected?.package_id}, version ${selected?.package_version}?`
              : `Use shipment ${booking?.booking_id}?`
          }
        />
      )}
    </section>
  );
}

function DhlConfirmation({ operation, description, onCancel, onConfirm }: {
  operation: Operation; description: string; onCancel: () => void; onConfirm: () => void;
}) {
  const dialog = useRef<HTMLDivElement>(null);
  const cancel = useRef<HTMLButtonElement>(null);
  useLayoutEffect(() => {
    const node = dialog.current!;
    const backgrounds = Array.from(document.body.children).filter(el => el !== node);
    const previous = backgrounds.map(el => el.hasAttribute('inert'));
    backgrounds.forEach(el => el.setAttribute('inert', ''));
    cancel.current?.focus();
    const contain = (event: FocusEvent) => {
      if (!node.contains(event.target as Node)) cancel.current?.focus();
    };
    document.addEventListener('focusin', contain);
    return () => {
      document.removeEventListener('focusin', contain);
      backgrounds.forEach((el, index) => { if (!previous[index]) el.removeAttribute('inert'); });
    };
  }, []);
  const action = operation === 'book' ? 'Create DHL shipment' : operation === 'handoff' ? 'Record DHL handoff' : 'Refresh DHL tracking';
  return createPortal(
    <div
      ref={dialog}
      role="dialog"
      aria-modal="true"
      aria-labelledby="dhl-confirm-title"
      aria-describedby="dhl-confirm-description"
      tabIndex={-1}
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/50 backdrop-blur-xs p-4"
      onKeyDown={event => {
        if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); onCancel(); }
        if (event.key === 'Tab') {
          const buttons = Array.from(dialog.current!.querySelectorAll<HTMLButtonElement>('button:not(:disabled)'));
          const index = buttons.indexOf(document.activeElement as HTMLButtonElement);
          event.preventDefault();
          buttons[(index + (event.shiftKey ? buttons.length - 1 : 1)) % buttons.length]?.focus();
        }
      }}
    >
      <div className="w-full max-w-lg max-h-[90vh] overflow-auto rounded-2xl bg-white p-6 shadow-xl border border-gray-100 space-y-4">
        <div className="flex items-center gap-2.5">
          <span className="inline-flex items-center justify-center w-8 h-8 rounded-full bg-amber-100 text-amber-900 text-sm font-bold">
            ⚠️
          </span>
          <h3 id="dhl-confirm-title" className="text-lg font-bold text-gray-900">
            Confirm DHL {operation === 'book' ? 'shipment creation' : operation === 'handoff' ? 'hub handoff' : 'tracking refresh'}
          </h3>
        </div>
        <p id="dhl-confirm-description" className="text-sm text-gray-600 break-words leading-relaxed">
          {description}
        </p>
        <div className="flex flex-wrap justify-end gap-2.5 pt-2 border-t border-gray-100">
          <button ref={cancel} className={btnSecondary} onClick={onCancel}>
            Cancel
          </button>
          <button
            className={operation === 'book' ? btnAmber : btnPrimary}
            onClick={onConfirm}
          >
            {action}
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
}
