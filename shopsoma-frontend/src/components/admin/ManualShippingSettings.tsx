import { useEffect, useState, type FormEvent } from 'react';
import axios from 'axios';
import {
  getManualShippingRates, saveManualShippingRate, deactivateManualShippingRate,
  setDefaultManualShippingRate, previewManualShippingRates,
  type ManualShippingRate, type ManualShippingRateInput,
} from '../../services/settingsService';

const blank: ManualShippingRateInput = {
  name: '', description: '', country: 'Nigeria', state: null, base_rate: 0,
  min_order_value: 0, max_order_value: null, min_delivery_days: 2,
  max_delivery_days: 5, is_active: true, is_default: false, priority: 0,
};
const failure = (error: unknown) => {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail;
    if (typeof detail === 'string') return detail;
    if (detail?.message) return detail.message;
  }
  return 'Unable to save or load shipping rates. Check the fields and retry.';
};

export default function ManualShippingSettings() {
  const [rates, setRates] = useState<ManualShippingRate[]>([]);
  const [form, setForm] = useState<ManualShippingRateInput>({ ...blank });
  const [editing, setEditing] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [preview, setPreview] = useState({ country: 'Nigeria', state: 'Lagos', order_value: 60000 });
  const [options, setOptions] = useState<ManualShippingRate[] | null>(null);
  const reload = async () => setRates(await getManualShippingRates());
  useEffect(() => { void reload().catch(e => setError(failure(e))).finally(() => setLoading(false)); }, []);
  const change = <K extends keyof ManualShippingRateInput>(key: K, value: ManualShippingRateInput[K]) =>
    setForm(previous => ({ ...previous, [key]: value }));
  const run = async (action: () => Promise<unknown>, success: string) => {
    setBusy(true); setError(''); setMessage('');
    try { await action(); await reload(); setOptions(null); setMessage(success); }
    catch (e) { setError(failure(e)); }
    finally { setBusy(false); }
  };
  const save = (event: FormEvent) => {
    event.preventDefault();
    if (!form.name.trim() || !form.country.trim()
      || (form.max_order_value !== null && form.max_order_value < (form.min_order_value ?? 0))
      || form.max_delivery_days < form.min_delivery_days) {
      setError('Enter a name and country, and ensure each maximum is at least its minimum.'); return;
    }
    void run(async () => {
      await saveManualShippingRate(form, editing);
      setForm({ ...blank }); setEditing(undefined);
    }, 'Shipping rate saved and reloaded.');
  };
  const inputClass = 'mt-1 w-full rounded-lg border border-gray-300 p-2 text-sm';
  return <section aria-label="Manual shipping rates" className="rounded-2xl border border-gray-200 bg-white p-6 space-y-4">
    <h2 className="text-lg font-semibold">Manual shipping rates</h2>
    <p className="text-sm text-gray-600">Prices and subtotal ranges are in NGN. USD quotes use the server exchange rate. Fulfilment is manual; saving a rate does not book a carrier. Edits affect new quotes only; issued quotes keep their price until expiry.</p>
    {error && <p role="alert" className="text-red-700">{error}</p>}
    {message && <p role="status" className="text-green-700">{message}</p>}
    {loading ? <p role="status">Loading shipping rates…</p> : <>
      <button type="button" disabled={busy} onClick={() => void run(reload, 'Rates reloaded.')} className="text-sm underline">Reload rates</button>
      {rates.length === 0 && <p>No manual rates configured. Add an active rate before accepting orders.</p>}
      <ul className="space-y-2">{rates.map(rate => <li key={rate.id} className="rounded-lg border p-3 flex flex-wrap gap-3 items-center">
        <span className="flex-1">{rate.name} — NGN {Number(rate.base_rate).toFixed(2)} · {rate.country}, {rate.state || 'All states'} · {rate.min_delivery_days}–{rate.max_delivery_days} days · Priority {rate.priority} · {rate.is_active ? 'Active' : 'Inactive'}{rate.is_default ? ' · Default' : ''}</span>
        <button type="button" disabled={busy} onClick={() => { setEditing(rate.id); setForm({ ...rate }); setError(''); setMessage(''); }} className="underline">Edit {rate.name}</button>
        {rate.is_active && <>
          <button type="button" disabled={busy || rate.is_default} onClick={() => void run(() => setDefaultManualShippingRate(rate.id), 'Default rate saved.')} className="underline">Set default {rate.name}</button>
          <button type="button" disabled={busy} onClick={() => void run(() => deactivateManualShippingRate(rate.id), 'Rate deactivated. Issued quotes are unchanged.')} className="text-red-700 underline">Deactivate {rate.name}</button>
        </>}
      </li>)}</ul>
    </>}
    <form onSubmit={save} className="space-y-4">
      <h3 className="font-semibold">{editing ? 'Edit rate' : 'Add rate'}</h3>
      <fieldset disabled={busy || loading} className="grid gap-3 sm:grid-cols-2">
        <label>Rate name<input required maxLength={100} className={inputClass} value={form.name} onChange={e => change('name', e.target.value)} /></label>
        <label>Description<input maxLength={500} className={inputClass} value={form.description ?? ''} onChange={e => change('description', e.target.value)} /></label>
        <label>Country<input required className={inputClass} value={form.country} onChange={e => change('country', e.target.value)} /></label>
        <label>State (blank for all)<input className={inputClass} value={form.state ?? ''} onChange={e => change('state', e.target.value || null)} /></label>
        {([
          ['base_rate', 'Price (NGN)', 0, '0.01'],
          ['min_order_value', 'Minimum subtotal (NGN)', 0, '0.01'],
          ['max_order_value', 'Maximum subtotal (NGN, optional)', 0, '0.01'],
          ['min_delivery_days', 'Minimum delivery days', 1, '1'],
          ['max_delivery_days', 'Maximum delivery days', 1, '1'],
          ['priority', 'Priority (lower first)', undefined, '1'],
        ] as const).map(([key, label, min, step]) => <label key={key}>{label}<input type="number" required={key !== 'max_order_value' && key !== 'min_order_value'} min={min} step={step} className={inputClass} value={form[key] ?? ''} onChange={e => change(key, e.target.value === '' && (key === 'max_order_value' || key === 'min_order_value') ? null : Number(e.target.value))} /></label>)}
        <label><input type="checkbox" checked={form.is_active} onChange={e => setForm(previous => ({ ...previous, is_active: e.target.checked, is_default: e.target.checked && previous.is_default }))} /> Active</label>
        <label><input type="checkbox" disabled={!form.is_active} checked={form.is_default} onChange={e => change('is_default', e.target.checked)} /> Default</label>
      </fieldset>
      <button disabled={busy || loading} className="rounded-lg bg-[#105E53] text-white px-4 py-2">{busy ? 'Saving…' : 'Save shipping rate'}</button>
      {editing && <button type="button" disabled={busy} className="ml-3 underline" onClick={() => { setEditing(undefined); setForm({ ...blank }); }}>Cancel edit</button>}
    </form>
    <form className="border-t pt-4 space-y-3" onSubmit={event => {
      event.preventDefault(); setBusy(true); setError(''); setOptions(null);
      void previewManualShippingRates(preview).then(result => setOptions(result.available_rates)).catch(e => setError(failure(e))).finally(() => setBusy(false));
    }}>
      <h3 className="font-semibold">Preview saved rates</h3>
      <div className="grid gap-3 sm:grid-cols-3">
        <label>Preview country<input required className={inputClass} value={preview.country} onChange={e => setPreview({ ...preview, country: e.target.value })} /></label>
        <label>Preview state<input required className={inputClass} value={preview.state} onChange={e => setPreview({ ...preview, state: e.target.value })} /></label>
        <label>Preview subtotal (NGN)<input required type="number" min="0.01" step="0.01" className={inputClass} value={preview.order_value} onChange={e => setPreview({ ...preview, order_value: Number(e.target.value) })} /></label>
      </div>
      <button disabled={busy} className="underline">Preview shipping</button>
      {options && <ul aria-label="Preview results">{options.map(rate => <li key={rate.id}>{rate.name}: NGN {Number(rate.base_rate).toFixed(2)} · {rate.min_delivery_days}–{rate.max_delivery_days} business days</li>)}</ul>}
    </form>
  </section>;
}
