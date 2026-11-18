import { useEffect, useMemo, useState } from 'react';
import type { DhlOperationPackage, OrderDetail } from '../../services/adminOrderService';
import {
  describeApiError,
  evaluateParcel,
  getShippingBoxPresets,
  recordDhlParcelMeasurement,
  type ShippingBoxPreset,
} from '../../services/parcelMeasurementService';

const CUSTOM = '__custom__';
const fieldClass = 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-[#105E53] focus:ring-2 focus:ring-[#105E53] disabled:bg-gray-100';

const fmt = (value: number | string | null | undefined, digits = 2) => {
  const n = Number(value);
  return Number.isFinite(n) ? n.toFixed(digits).replace(/\.?0+$/, '') : '—';
};

/**
 * Record the real packed parcel (hub scale weight + box dimensions) so the DHL
 * label is booked with measurements DHL will accept and bill correctly.
 */
export default function DhlParcelMeasurementCard({ order, pkg, disabled, onOrderChange }: {
  order: OrderDetail;
  /** Selected ready package, or undefined when no package has been prepared yet. */
  pkg?: DhlOperationPackage;
  disabled?: boolean;
  onOrderChange: (order: OrderDetail) => void;
}) {
  const parcel = pkg?.parcel ?? null;
  const measured = parcel?.measurement_source === 'hub_measured';
  const booked = !!pkg?.selection_blockers.some(b => b === 'active_booking_exists' || b === 'custody_handed_off');

  const [presets, setPresets] = useState<ShippingBoxPreset[]>([]);
  const [presetsDefault, setPresetsDefault] = useState(false);
  const [presetError, setPresetError] = useState('');
  const [box, setBox] = useState('');
  const [weight, setWeight] = useState('');
  const [dims, setDims] = useState({ length_cm: '', width_cm: '', height_cm: '' });
  const [weighed, setWeighed] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ tone: 'ok' | 'error'; text: string } | null>(null);
  const [editing, setEditing] = useState(false);

  useEffect(() => {
    let active = true;
    getShippingBoxPresets()
      .then(res => { if (active) { setPresets(res.presets.filter(p => p.is_active)); setPresetsDefault(res.is_default); } })
      .catch(() => { if (active) setPresetError('Box sizes could not be loaded; enter dimensions manually.'); });
    return () => { active = false; };
  }, []);

  // Reset the form whenever the package version changes (new measurement saved).
  useEffect(() => {
    setWeighed(false);
    setEditing(false);
    if (measured && parcel) {
      setBox(parcel.box_preset_code ?? CUSTOM);
      setWeight(fmt(parcel.weight_kg, 3));
      setDims({ length_cm: fmt(parcel.length_cm, 0), width_cm: fmt(parcel.width_cm, 0), height_cm: fmt(parcel.height_cm, 0) });
    } else {
      setBox('');
      setWeight('');
      setDims({ length_cm: '', width_cm: '', height_cm: '' });
    }
  }, [pkg?.package_id, pkg?.package_version]); // eslint-disable-line react-hooks/exhaustive-deps

  const selectedPreset = presets.find(p => p.code === box);
  const contentsKg = parcel?.estimated_contents_weight_kg != null ? Number(parcel.estimated_contents_weight_kg) : null;
  const suggestedKg = contentsKg != null && selectedPreset ? contentsKg + Number(selectedPreset.tare_weight_kg) : contentsKg;
  const evaluation = useMemo(() => evaluateParcel({ weight_kg: weight, ...dims }), [weight, dims]);
  const lowVsSuggested = suggestedKg != null && evaluation.weightKg != null && evaluation.weightKg < suggestedKg * 0.5;

  const chooseBox = (code: string) => {
    setBox(code);
    const preset = presets.find(p => p.code === code);
    if (preset) {
      setDims({ length_cm: String(preset.length_cm), width_cm: String(preset.width_cm), height_cm: String(preset.height_cm) });
    }
  };

  const formOpen = !booked && (!measured || editing);
  const canSave = formOpen && !disabled && !saving && box !== '' && weighed && evaluation.errors.length === 0;

  async function save() {
    if (!canSave) return;
    setSaving(true);
    setMessage(null);
    try {
      const fresh = await recordDhlParcelMeasurement(order.id, {
        box_preset_code: box === CUSTOM ? null : box,
        weight_kg: weight.trim(),
        ...dims,
      });
      onOrderChange(fresh);
      setMessage({ tone: 'ok', text: 'Parcel measurements saved. The DHL shipment will be booked with these values.' });
    } catch (error) {
      setMessage({ tone: 'error', text: describeApiError(error, 'Parcel measurements could not be saved. Refresh the order and try again.') });
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4 space-y-3" aria-labelledby="dhl-parcel-title">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 id="dhl-parcel-title" className="text-sm font-semibold text-gray-900">Parcel weight &amp; dimensions</h3>
        {parcel && (
          <span
            className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-semibold border ${measured ? 'bg-emerald-50 text-emerald-800 border-emerald-200' : 'bg-amber-50 text-amber-900 border-amber-200'}`}
          >
            {measured ? 'Hub measured' : 'Estimated — not yet measured'}
          </span>
        )}
      </div>

      {parcel && (
        <dl className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
          <div><dt className="text-gray-500">Weight</dt><dd className="font-medium text-gray-900">{fmt(parcel.weight_kg, 3)} kg</dd></div>
          <div><dt className="text-gray-500">Dimensions</dt><dd className="font-medium text-gray-900">{fmt(parcel.length_cm, 0)} × {fmt(parcel.width_cm, 0)} × {fmt(parcel.height_cm, 0)} cm</dd></div>
          <div><dt className="text-gray-500">Volumetric</dt><dd className="font-medium text-gray-900">{fmt(parcel.volumetric_weight_kg)} kg</dd></div>
          <div><dt className="text-gray-500">DHL billable</dt><dd className="font-semibold text-gray-900">{fmt(parcel.billable_weight_kg, 1)} kg</dd></div>
        </dl>
      )}

      {!parcel && (
        <p className="text-xs text-gray-600">Pack and seal the order, then record what the scale reads. This prepares the hub package with the real measurements.</p>
      )}
      {parcel && !measured && !booked && (
        <p className="text-xs text-amber-900">These values come from vendor catalog data or category estimates. Weigh and measure the sealed parcel before creating the DHL shipment.</p>
      )}
      {booked && measured && (
        <p className="text-xs text-gray-600">The DHL shipment was booked with these measurements. They can no longer be changed here.</p>
      )}

      {measured && !booked && !editing && (
        <button type="button" className="text-xs font-medium text-[#105E53] underline disabled:opacity-50" disabled={disabled} onClick={() => setEditing(true)}>
          Re-measure parcel
        </button>
      )}

      {formOpen && (
        <div className="space-y-3 border-t border-gray-100 pt-3">
          {presetsDefault && (
            <p className="text-[11px] text-gray-500">Using default box sizes. Save ShopSoma's real boxes under Admin settings → Shipping boxes.</p>
          )}
          {presetError && <p className="text-[11px] text-amber-800">{presetError}</p>}
          <div className="space-y-1">
            <label htmlFor="dhl-parcel-box" className="block text-xs font-medium text-gray-700">ShopSoma box</label>
            <select id="dhl-parcel-box" className={fieldClass} value={box} disabled={disabled || saving} onChange={e => chooseBox(e.target.value)}>
              <option value="">Select the box used</option>
              {presets.map(p => (
                <option key={p.code} value={p.code}>{p.name} — {fmt(p.length_cm, 0)}×{fmt(p.width_cm, 0)}×{fmt(p.height_cm, 0)} cm</option>
              ))}
              <option value={CUSTOM}>Other / custom size</option>
            </select>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="space-y-1">
              <label htmlFor="dhl-parcel-weight" className="block text-xs font-medium text-gray-700">Scale weight (kg)</label>
              <input id="dhl-parcel-weight" type="number" inputMode="decimal" min="0.01" max="70" step="0.001" className={fieldClass} value={weight} disabled={disabled || saving} onChange={e => setWeight(e.target.value)} />
            </div>
            {([['length_cm', 'Length (cm)'], ['width_cm', 'Width (cm)'], ['height_cm', 'Height (cm)']] as const).map(([key, label]) => (
              <div key={key} className="space-y-1">
                <label htmlFor={`dhl-parcel-${key}`} className="block text-xs font-medium text-gray-700">{label}</label>
                <input
                  id={`dhl-parcel-${key}`}
                  type="number"
                  inputMode="decimal"
                  min="1"
                  step="0.1"
                  className={fieldClass}
                  value={dims[key]}
                  disabled={disabled || saving || (box !== CUSTOM && !!selectedPreset)}
                  onChange={e => setDims(prev => ({ ...prev, [key]: e.target.value }))}
                />
              </div>
            ))}
          </div>
          {suggestedKg != null && (
            <p className="text-[11px] text-gray-500">
              Catalog estimate{selectedPreset ? ' incl. empty box' : ''}: ~{fmt(suggestedKg, 2)} kg. Always enter the actual scale reading.
            </p>
          )}
          {lowVsSuggested && (
            <p role="alert" className="text-[11px] text-amber-800">Scale weight is less than half the catalog estimate. Double-check the reading and that every item is in the parcel.</p>
          )}
          {weight.trim() && evaluation.errors.length > 0 && (
            <ul role="alert" className="text-[11px] text-red-700 list-disc pl-4">
              {evaluation.errors.map(e => <li key={e}>{e}</li>)}
            </ul>
          )}
          {evaluation.dims && evaluation.errors.length === 0 && (
            <p className="text-xs text-gray-700">
              DHL will receive {evaluation.dims.join(' × ')} cm, {fmt(evaluation.weightKg, 3)} kg · volumetric {fmt(evaluation.volumetricKg)} kg · <span className="font-semibold">billable {fmt(evaluation.billableKg, 1)} kg</span>
            </p>
          )}
          <label className="flex items-start gap-2 text-xs text-gray-700">
            <input type="checkbox" className="mt-0.5" checked={weighed} disabled={disabled || saving} onChange={e => setWeighed(e.target.checked)} />
            <span>I weighed the sealed parcel on the hub scale and confirmed the box size.</span>
          </label>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              className="inline-flex items-center justify-center px-4 py-2 rounded-lg text-sm font-medium bg-[#105E53] hover:bg-[#0d4a41] text-white disabled:opacity-50 disabled:cursor-not-allowed"
              disabled={!canSave}
              onClick={save}
            >
              {saving ? 'Saving…' : 'Save parcel measurements'}
            </button>
            {editing && (
              <button type="button" className="px-3 py-2 text-sm text-gray-600" disabled={saving} onClick={() => setEditing(false)}>Cancel</button>
            )}
          </div>
        </div>
      )}

      {message && (
        <p role="status" className={`text-xs ${message.tone === 'ok' ? 'text-emerald-700' : 'text-red-700'}`}>{message.text}</p>
      )}
    </div>
  );
}
