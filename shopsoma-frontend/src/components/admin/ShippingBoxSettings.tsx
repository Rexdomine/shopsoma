import { useEffect, useState } from 'react';
import {
  describeApiError,
  evaluateParcel,
  getShippingBoxPresets,
  updateShippingBoxPresets,
  type ShippingBoxPreset,
} from '../../services/parcelMeasurementService';

type Row = { code: string; name: string; length_cm: string; width_cm: string; height_cm: string; tare_weight_kg: string; is_active: boolean };

const toRow = (p: ShippingBoxPreset): Row => ({
  code: p.code,
  name: p.name,
  length_cm: String(p.length_cm),
  width_cm: String(p.width_cm),
  height_cm: String(p.height_cm),
  tare_weight_kg: String(p.tare_weight_kg ?? '0'),
  is_active: p.is_active,
});

const cell = 'w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm';

function rowErrors(row: Row): string[] {
  const errors: string[] = [];
  if (!/^[A-Za-z0-9][A-Za-z0-9_-]{0,49}$/.test(row.code.trim())) errors.push('Code: letters, numbers, - or _');
  if (!row.name.trim()) errors.push('Name is required');
  const tare = Number(row.tare_weight_kg || '0');
  if (!Number.isFinite(tare) || tare < 0 || tare > 20) errors.push('Empty box weight must be 0–20 kg');
  const dims = evaluateParcel({ weight_kg: '1', length_cm: row.length_cm, width_cm: row.width_cm, height_cm: row.height_cm });
  return [...errors, ...dims.errors];
}

/** Admin editor for ShopSoma's standard shipping boxes (used to pre-fill hub measurements). */
export default function ShippingBoxSettings() {
  const [rows, setRows] = useState<Row[]>([]);
  const [isDefault, setIsDefault] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [message, setMessage] = useState<{ tone: 'ok' | 'error'; text: string } | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const res = await getShippingBoxPresets();
      setRows(res.presets.map(toRow));
      setIsDefault(res.is_default);
      setDirty(false);
    } catch (error) {
      setMessage({ tone: 'error', text: describeApiError(error, 'Shipping boxes could not be loaded.') });
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { void load(); }, []);

  const update = (index: number, patch: Partial<Row>) => {
    setRows(prev => prev.map((row, i) => (i === index ? { ...row, ...patch } : row)));
    setDirty(true);
    setMessage(null);
  };

  const errors = rows.map(rowErrors);
  const codes = rows.map(r => r.code.trim().toUpperCase());
  const duplicate = codes.some((c, i) => c && codes.indexOf(c) !== i);
  const valid = rows.length > 0 && errors.every(e => e.length === 0) && !duplicate && rows.some(r => r.is_active);

  const save = async () => {
    if (!valid || saving) return;
    setSaving(true);
    setMessage(null);
    try {
      const res = await updateShippingBoxPresets(rows.map(r => ({
        code: r.code.trim(),
        name: r.name.trim(),
        length_cm: r.length_cm,
        width_cm: r.width_cm,
        height_cm: r.height_cm,
        tare_weight_kg: r.tare_weight_kg || '0',
        is_active: r.is_active,
      })));
      setRows(res.presets.map(toRow));
      setIsDefault(false);
      setDirty(false);
      setMessage({ tone: 'ok', text: 'Shipping boxes saved. Dimensions are stored in whole centimetres, as DHL measures them.' });
    } catch (error) {
      setMessage({ tone: 'error', text: describeApiError(error, 'Shipping boxes could not be saved.') });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-7">
      <p className="text-xs font-bold uppercase tracking-[0.16em] text-[#105E53]">DHL parcels</p>
      <h2 className="mt-1 text-2xl font-semibold text-slate-950">Shipping boxes</h2>
      <p className="mt-1 text-sm text-slate-600">
        ShopSoma's standard boxes. Hub staff pick a box when measuring a sealed parcel, so its outside dimensions fill in automatically. Enter the
        <strong> outside</strong> measurements and the empty box weight. Each box must fit DHL Express limits (longest side ≤ 120 cm, other sides ≤ 80 cm).
      </p>
      {isDefault && !loading && (
        <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
          These are placeholder sizes. Replace them with ShopSoma's real boxes and save.
        </div>
      )}
      {loading ? (
        <p className="mt-6 text-sm text-slate-500">Loading boxes…</p>
      ) : (
        <div className="mt-6 overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="text-xs uppercase text-slate-500">
              <tr>
                <th className="pb-2 pr-2">Code</th><th className="pb-2 pr-2">Name</th>
                <th className="pb-2 pr-2">L (cm)</th><th className="pb-2 pr-2">W (cm)</th><th className="pb-2 pr-2">H (cm)</th>
                <th className="pb-2 pr-2">Empty box (kg)</th><th className="pb-2 pr-2">Active</th><th className="pb-2" />
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => (
                <tr key={index} className="align-top">
                  <td className="py-1 pr-2 w-28"><input aria-label={`Box ${index + 1} code`} className={cell} value={row.code} onChange={e => update(index, { code: e.target.value })} /></td>
                  <td className="py-1 pr-2 min-w-[10rem]">
                    <input aria-label={`Box ${index + 1} name`} className={cell} value={row.name} onChange={e => update(index, { name: e.target.value })} />
                    {errors[index].length > 0 && <p className="mt-1 text-[11px] text-red-700">{errors[index].join('. ')}</p>}
                  </td>
                  {(['length_cm', 'width_cm', 'height_cm', 'tare_weight_kg'] as const).map(key => (
                    <td key={key} className="py-1 pr-2 w-24">
                      <input aria-label={`Box ${index + 1} ${key}`} type="number" min="0" step={key === 'tare_weight_kg' ? '0.01' : '0.1'} className={cell} value={row[key]} onChange={e => update(index, { [key]: e.target.value })} />
                    </td>
                  ))}
                  <td className="py-2 pr-2"><input aria-label={`Box ${index + 1} active`} type="checkbox" checked={row.is_active} onChange={e => update(index, { is_active: e.target.checked })} /></td>
                  <td className="py-1"><button type="button" className="text-xs text-red-700 disabled:opacity-40" disabled={rows.length <= 1} onClick={() => { setRows(prev => prev.filter((_, i) => i !== index)); setDirty(true); }}>Remove</button></td>
                </tr>
              ))}
            </tbody>
          </table>
          {duplicate && <p className="mt-2 text-xs text-red-700">Box codes must be unique.</p>}
          <button
            type="button"
            className="mt-3 text-sm font-medium text-[#105E53]"
            onClick={() => { setRows(prev => [...prev, { code: '', name: '', length_cm: '', width_cm: '', height_cm: '', tare_weight_kg: '0', is_active: true }]); setDirty(true); }}
          >
            + Add box
          </button>
        </div>
      )}
      <div className="mt-6 flex flex-wrap items-center gap-3">
        <button type="button" onClick={save} disabled={!dirty || !valid || saving} className="rounded-lg bg-[#105E53] px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-50">
          {saving ? 'Saving…' : 'Save shipping boxes'}
        </button>
        {dirty && <button type="button" onClick={() => void load()} disabled={saving} className="text-sm text-slate-600">Discard changes</button>}
        {message && <p role="status" className={`text-sm ${message.tone === 'ok' ? 'text-emerald-700' : 'text-red-700'}`}>{message.text}</p>}
      </div>
    </div>
  );
}
