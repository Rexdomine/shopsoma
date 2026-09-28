import { useEffect, useState } from 'react';
import { getCommerceFeatures, updateCommerceFeatures, type CommerceFeatures } from '../../services/settingsService';
import { useCurrencyStore } from '../../store/currencyStore';

export default function CommerceFeatureSettings() {
  const [flags, setFlags] = useState<CommerceFeatures | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const load = async () => {
    setBusy(true);
    setError('');
    try { setFlags(await getCommerceFeatures()); }
    catch { setError('Unable to load payment and currency settings. Retry to continue.'); }
    finally { setBusy(false); }
  };
  useEffect(() => { void load(); }, []);
  const change = async (key: keyof CommerceFeatures) => {
    if (!flags || busy) return;
    setBusy(true);
    setError('');
    setMessage('');
    try {
      const saved = await updateCommerceFeatures({ ...flags, [key]: !flags[key] });
      setFlags(saved);
      useCurrencyStore.getState().applyCommerceFeatures(saved);
      setMessage('Payment and currency settings saved.');
    } catch { setError('Unable to save settings. Reload before trying again.'); setFlags(null); }
    finally { setBusy(false); }
  };
  return <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-7" aria-label="Payment and currency availability">
    <h2 className="text-2xl font-semibold text-slate-950">Payment and currency availability</h2>
    <p className="mt-2 text-sm text-slate-600">Changes save immediately. Existing orders and payment processing keep their original values.</p>
    {error && <p role="alert" className="mt-4 text-sm text-red-700">{error}</p>}
    {message && <p role="status" className="mt-4 text-sm text-emerald-700">{message}</p>}
    {busy && <p role="status" className="mt-4 text-sm">Loading or saving settings…</p>}
    <div className="mt-5 space-y-4">
      {([
        ['stripe_enabled', 'Stripe payments enabled', 'Allow new Stripe payments. Paystack remains available for NGN.'],
        ['usd_switching_enabled', 'USD currency switching enabled', 'Allow shoppers to choose USD. When off, shopping and new checkout use NGN with currency conversion.'],
      ] as const).map(([key, label, hint]) => <label key={key} className="flex items-start gap-3">
        <input aria-label={label} type="checkbox" className="mt-1" checked={flags?.[key] ?? false} disabled={busy || !flags} onChange={() => void change(key)} />
        <span><span className="block font-semibold">{label}</span><span className="block text-sm text-slate-600">{hint}</span></span>
      </label>)}
    </div>
    {error && <button type="button" disabled={busy} onClick={() => void load()} className="mt-4 rounded-lg border px-4 py-2">Reload settings</button>}
  </section>;
}
