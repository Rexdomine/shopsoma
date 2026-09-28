import { useEffect, useRef, useState } from 'react';
import { createDhlBooking, getDhlLabel, getOrderDetail, recordDhlHandoff, refreshDhlTracking } from '../../services/adminOrderService';
import type { OrderDetail } from '../../services/adminOrderService';

type Operation = 'book' | 'handoff' | 'tracking';
const buttonClass = 'px-4 py-2 rounded border border-gray-300 disabled:opacity-50 disabled:cursor-not-allowed';
const unresolved = new Set(['in_progress', 'required', 'expired_claim_requires_recovery', 'inconsistent']);
const blockerCopy: Record<string, string> = {
  order_cancelled: 'Order cancelled', package_not_ready: 'Package is not ready',
  custody_handed_off: 'Package has left hub custody', active_seal_missing: 'Active seal unavailable',
  active_intent_missing: 'Shipment intent unavailable', selected_dhl_quote_missing: 'Selected DHL quote unavailable',
  active_booking_exists: 'Shipment attempt already exists', reconciliation_required: 'Reconciliation required',
  expired_claim_requires_recovery: 'Expired attempt requires authorized recovery',
  inconsistent_persisted_state: 'Shipment records require review',
};

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
  const [confirmation, setConfirmation] = useState<Operation | null>(null);
  const [busy, setBusy] = useState(false);
  const running = useRef(false);
  const [message, setMessage] = useState('');
  const [handoff, setHandoff] = useState({ occurred_at: '', counterparty: '', evidence_ref: '', evidence_sha256: '' });
  const packages = facts?.packages ?? [];
  const ready = packages.filter(p => p.package_state === 'ready');
  const selected = packages.find(p => p.package_id === (packageId || (ready.length === 1 ? ready[0].package_id : '')));
  const bookings = facts?.bookings ?? [];
  const booking = bookings.find(b => b.booking_id === (bookingId || (bookings.length === 1 ? bookings[0].booking_id : '')));
  const cancelled = order.fulfillment_status === 'cancelled';
  const locked = busy || disabled || confirmation !== null;
  const canBook = !!facts && !!selected?.selection_eligible && !!selected.intent_id && !!selected.seal_id && !held && !cancelled;
  const usableBooking = !!booking && booking.classification === 'success' && !unresolved.has(booking.reconciliation_state);

  async function reload() {
    const fresh = await getOrderDetail(order.id);
    onOrderChange(fresh);
    return fresh;
  }

  async function execute() {
    const op = confirmation;
    if (!op || running.current || disabled) return;
    if ((op === 'book' && !canBook) || (op !== 'book' && (!usableBooking || cancelled || held))) return;
    running.current = true;
    setBusy(true);
    setMessage('');
    setConfirmation(null);
    try {
      if (localStorage.getItem(storageKey) !== null) { setHeld(true); return; }
      const idempotency_key = crypto.randomUUID();
      setHeld(true);
      localStorage.setItem(storageKey, '1');
      if (op === 'book' && selected?.intent_id && selected.seal_id) {
        // Store only a safety marker, never shipment, command or private evidence payloads.
        // Persist before sending: an empty later GET cannot prove this command never started.
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
          ...handoff, occurred_at: new Date(handoff.occurred_at).toISOString(),
          counterparty: handoff.counterparty.trim(), evidence_ref: handoff.evidence_ref.trim(),
          evidence_sha256: handoff.evidence_sha256.trim().toLowerCase(), idempotency_key,
        });
        setHandoff({ occurred_at: '', counterparty: '', evidence_ref: '', evidence_sha256: '' });
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

  return <section className="bg-white rounded-lg shadow p-6 space-y-4" aria-labelledby="dhl-operations-title">
    <h2 id="dhl-operations-title" className="text-lg font-semibold">DHL Shipment Operations</h2>
    <p>DHL pickup booking is unavailable. Record handoff only after actual collection from the ShopSoma hub.</p>
    {!facts ? <p role="status">Shipment operations are unavailable until backend shipment facts can be loaded.</p> : <>
      <label className="block">Ready hub package
        <select className="block border rounded p-2 w-full" aria-label="Ready hub package" value={selected?.package_id ?? ''}
          disabled={locked} onChange={e => setPackageId(e.target.value)}>
          <option value="">Select ready package</option>
          {ready.map(p => <option key={p.package_id} value={p.package_id}>{p.package_id} · version {p.package_version} · hub {p.origin_hub_id}</option>)}
        </select>
      </label>
      {ready.length === 0 && <p>No ready hub packages.</p>}
      {selected && <p>Origin: ShopSoma hub {selected.origin_hub_id}. Package version {selected.package_version}.</p>}
      {selected?.selection_blockers.map(code => <p key={code}>{blockerCopy[code] ?? 'Shipment records require review'}</p>)}
      {held && <p role="alert">An unresolved local shipment command blocks new mutations, including after reload. Request authorized outcome review; an empty record does not prove no shipment was created.</p>}
      <button className={buttonClass} disabled={locked || !canBook} onClick={() => setConfirmation('book')}>Create DHL shipment</button>
      <label className="block">Shipment record
        <select className="block border rounded p-2 w-full" aria-label="Shipment record" value={booking?.booking_id ?? ''}
          disabled={locked} onChange={e => setBookingId(e.target.value)}>
          <option value="">Select shipment record</option>
          {bookings.map(b => <option key={b.booking_id} value={b.booking_id}>{b.booking_id} · {b.classification}</option>)}
        </select>
      </label>
      {!bookings.length && <p>No recorded DHL shipments.</p>}
      {booking && <div className="space-y-3">
        <p>Package {booking.package_id} · version {booking.package_version} · hub {booking.origin_hub_id}</p>
        <p>Shipment status: {booking.outbound_state}. Outcome: {booking.classification}.</p>
        {booking.tracking_number && <p>Tracking number: {booking.tracking_number}</p>}
        {unresolved.has(booking.reconciliation_state) && <p role="alert">This attempt requires review ({booking.reconciliation_state.replaceAll('_', ' ')}). Booking retries are unavailable.</p>}
        <div className="flex flex-wrap gap-2">
          <button className={buttonClass} disabled={locked || !booking.label_available} onClick={downloadLabel}>Download DHL label</button>
          <button className={buttonClass} disabled={locked || !usableBooking || cancelled || held} onClick={() => setConfirmation('tracking')}>Refresh DHL tracking</button>
        </div>
        {booking.handoff_recorded_at ? <p>Handoff recorded: {booking.handoff_recorded_at}</p> : <form className="space-y-2" onSubmit={e => {
          e.preventDefault();
          const ref = handoff.evidence_ref.trim();
          if (ref.includes('://') || ref.startsWith('/') || ref.includes('..') || !handoff.counterparty.trim() || !ref) {
            setMessage('Enter a private evidence reference and counterparty. URLs and absolute paths are not accepted.'); return;
          }
          setConfirmation('handoff');
        }}>
          <fieldset disabled={locked || !usableBooking || cancelled || held} className="space-y-2">
            <legend className="font-medium">Record hub-to-DHL handoff</legend>
            <label className="block">Collection time (your local time)<input className="block border p-2" required type="datetime-local" value={handoff.occurred_at} onChange={e => setHandoff({ ...handoff, occurred_at: e.target.value })} /></label>
            <label className="block">Counterparty<input className="block border p-2" required maxLength={120} autoComplete="off" value={handoff.counterparty} onChange={e => setHandoff({ ...handoff, counterparty: e.target.value })} /></label>
            <label className="block">Private evidence reference<input className="block border p-2" required maxLength={200} autoComplete="off" value={handoff.evidence_ref} onChange={e => setHandoff({ ...handoff, evidence_ref: e.target.value })} /></label>
            <label className="block">Evidence SHA-256<input className="block border p-2 w-full" required pattern="[a-fA-F0-9]{64}" maxLength={64} autoComplete="off" value={handoff.evidence_sha256} onChange={e => setHandoff({ ...handoff, evidence_sha256: e.target.value })} /></label>
            <p>Requires verified DHL collection tracking and valid hub custody. Evidence is sent privately and is not saved in browser storage.</p>
            <button className={buttonClass} type="submit">Record DHL handoff</button>
          </fieldset>
        </form>}
      </div>}
    </>}
    <button className={buttonClass} disabled={locked} onClick={async () => {
      if (running.current) return;
      running.current = true; setBusy(true);
      try { await reload(); setMessage('Shipment records refreshed.'); }
      catch { setMessage('Shipment records could not be refreshed. Existing safety restrictions remain.'); }
      finally { running.current = false; setBusy(false); }
    }}>Reload shipment records</button>
    {busy && <p role="status">DHL operation in progress…</p>}
    {message && <p role="status">{message}</p>}
    {confirmation && <div role="dialog" aria-modal="true" aria-labelledby="dhl-confirm-title" className="border-2 rounded p-4 space-y-3">
      <h3 id="dhl-confirm-title">Confirm DHL {confirmation === 'book' ? 'shipment creation' : confirmation === 'handoff' ? 'hub handoff' : 'tracking refresh'}</h3>
      <p>{confirmation === 'book' ? `Create a shipment from hub ${selected?.origin_hub_id} for package ${selected?.package_id}, version ${selected?.package_version}?` : `Use shipment ${booking?.booking_id}?`}</p>
      <button className={buttonClass} autoFocus disabled={busy} onClick={execute}>Confirm</button>{' '}
      <button className={buttonClass} disabled={busy} onClick={() => setConfirmation(null)}>Cancel</button>
    </div>}
  </section>;
}
