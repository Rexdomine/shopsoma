import { useEffect, useState } from 'react';
import { Clock, Loader2, RotateCcw, Save } from 'lucide-react';
import {
  getAdminCheckoutHoldSettings,
  updateCheckoutHoldSettings,
  type CheckoutHoldSettings as CheckoutHoldSettingsValue,
} from '../../services/settingsService';
import { useToast } from '../../hooks/useToast';
import ToastContainer from '../ui/ToastContainer';

interface CheckoutHoldSettingsProps {
  onDirtyChange?: (dirty: boolean) => void;
  onBusyChange?: (busy: boolean) => void;
}

export default function CheckoutHoldSettings({
  onDirtyChange,
  onBusyChange,
}: CheckoutHoldSettingsProps) {
  const { toasts, hideToast, success, error } = useToast();
  const [settings, setSettings] = useState<CheckoutHoldSettingsValue | null>(null);
  const [ttlInput, setTtlInput] = useState('30');
  const [graceInput, setGraceInput] = useState('15');
  const [releaseOnClose, setReleaseOnClose] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const applySaved = (value: CheckoutHoldSettingsValue) => {
    setSettings(value);
    setTtlInput(String(value.reservation_ttl_minutes));
    setGraceInput(String(value.authorization_grace_minutes));
    setReleaseOnClose(Boolean(value.release_on_payment_close));
  };

  useEffect(() => {
    getAdminCheckoutHoldSettings()
      .then(applySaved)
      .catch((err: any) => {
        error(err?.response?.data?.detail || 'Failed to load checkout hold settings', 'Error');
      })
      .finally(() => setLoading(false));
  }, [error]);

  const dirty = Boolean(settings) && (
    ttlInput !== String(settings?.reservation_ttl_minutes)
    || graceInput !== String(settings?.authorization_grace_minutes)
    || releaseOnClose !== Boolean(settings?.release_on_payment_close)
  );

  useEffect(() => {
    onDirtyChange?.(dirty);
    onBusyChange?.(saving);
    return () => {
      onDirtyChange?.(false);
      onBusyChange?.(false);
    };
  }, [dirty, saving, onBusyChange, onDirtyChange]);

  const handleDiscard = () => {
    if (settings) {
      applySaved(settings);
    }
  };

  const handleSave = async () => {
    const ttl = Number(ttlInput);
    const grace = Number(graceInput);

    if (!Number.isInteger(ttl) || ttl < 1 || ttl > 30) {
      error('Stock reservation hold must be a whole number between 1 and 30 minutes.', 'Invalid Input');
      return;
    }
    if (!Number.isInteger(grace) || grace < 0 || grace > 15) {
      error('Payment authorization grace must be a whole number between 0 and 15 minutes.', 'Invalid Input');
      return;
    }

    try {
      setSaving(true);
      const updated = await updateCheckoutHoldSettings({
        reservation_ttl_minutes: ttl,
        authorization_grace_minutes: grace,
        release_on_payment_close: releaseOnClose,
      });
      applySaved(updated);
      success('Checkout stock hold settings updated.', 'Success');
    } catch (err: any) {
      error(err?.response?.data?.detail || 'Failed to save checkout hold settings', 'Error');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <>
        <div className="flex items-center gap-3 rounded-2xl border border-slate-200 bg-white p-7 text-sm text-slate-600">
          <Loader2 className="h-5 w-5 animate-spin" />
          Loading checkout hold settings…
        </div>
        <ToastContainer toasts={toasts} onClose={hideToast} />
      </>
    );
  }

  const parsedTtl = Number.parseInt(ttlInput, 10);
  const parsedGrace = Number.parseInt(graceInput, 10);
  const draftTotalMinutes =
    Number.isFinite(parsedTtl) && Number.isFinite(parsedGrace)
      ? Math.max(0, parsedTtl) + Math.max(0, parsedGrace)
      : null;

  const savedTotalMinutes = settings
    ? settings.reservation_ttl_minutes + settings.authorization_grace_minutes
    : 45;

  return (
    <>
      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-7 space-y-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.16em] text-[#105E53]">
              Checkout inventory
            </p>
            <h2 className="mt-1 text-2xl font-semibold text-slate-950">
              Checkout stock holds
            </h2>
            <p className="mt-1 max-w-2xl text-sm text-slate-600">
              Control how long items are reserved during payment and whether closing the Paystack modal immediately checks and releases abandoned holds. Changes apply to new checkouts and payment attempts.
            </p>
          </div>
          {settings && (
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 min-w-[220px]">
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                Current effective hold
              </p>
              <p className="mt-2 text-xl font-semibold text-slate-950">
                {savedTotalMinutes} minutes
              </p>
              <p className="mt-1 text-xs text-slate-500">
                {settings.reservation_ttl_minutes}m reservation + {settings.authorization_grace_minutes}m grace
                {' · '}
                {settings.release_on_payment_close ? 'Release on modal close' : 'Hold until expiry'}
              </p>
            </div>
          )}
        </div>

        <div className="grid gap-5 sm:grid-cols-2">
          <label htmlFor="checkout-reservation-ttl" className="block text-sm font-semibold text-slate-800">
            Stock reservation hold (minutes)
            <input
              id="checkout-reservation-ttl"
              type="number"
              min={1}
              max={30}
              step={1}
              value={ttlInput}
              onChange={(e) => setTtlInput(e.target.value)}
              className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-2.5 text-slate-900"
            />
            <span className="mt-1 block text-xs font-normal text-slate-500">
              Allowed range: 1–30 minutes. Initial hold created when a delivery option is selected.
            </span>
          </label>

          <label htmlFor="checkout-authorization-grace" className="block text-sm font-semibold text-slate-800">
            Payment authorization grace (minutes)
            <input
              id="checkout-authorization-grace"
              type="number"
              min={0}
              max={15}
              step={1}
              value={graceInput}
              onChange={(e) => setGraceInput(e.target.value)}
              className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-2.5 text-slate-900"
            />
            <span className="mt-1 block text-xs font-normal text-slate-500">
              Allowed range: 0–15 minutes. Extra window after payment expires for delayed bank/card confirmations.
            </span>
          </label>
        </div>

        <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 flex items-center gap-3 text-sm text-slate-700">
          <Clock className="h-4 w-4 shrink-0 text-[#105E53]" />
          <span>
            {draftTotalMinutes !== null
              ? `Maximum unpaid hold with current draft: ${draftTotalMinutes} minutes total.`
              : 'Enter whole-minute numbers to preview total hold duration.'}
          </span>
        </div>

        <label className="flex items-start gap-3 rounded-xl border border-slate-200 p-4 cursor-pointer hover:bg-slate-50/70">
          <input
            type="checkbox"
            checked={releaseOnClose}
            onChange={(e) => setReleaseOnClose(e.target.checked)}
            className="mt-1"
          />
          <span>
            <span className="block text-sm font-semibold text-slate-900">
              Release stock when Paystack modal is closed without paying
            </span>
            <span className="mt-0.5 block text-xs text-slate-600">
              When enabled, closing the Paystack payment popup immediately verifies the transaction with Paystack and releases reserved stock back to the storefront if the payment was abandoned (completed payments still finalize normally).
            </span>
          </span>
        </label>

        <div className="flex flex-wrap items-center gap-3 border-t border-slate-100 pt-5">
          <button
            type="button"
            onClick={handleSave}
            disabled={!dirty || saving}
            className="inline-flex items-center gap-2 rounded-lg bg-[#105E53] px-4 py-2.5 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40"
          >
            <Save className="h-4 w-4" />
            {saving ? 'Saving…' : 'Save changes'}
          </button>
          <button
            type="button"
            onClick={handleDiscard}
            disabled={!dirty || saving}
            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 px-4 py-2.5 text-sm font-semibold text-slate-700 disabled:opacity-40"
          >
            <RotateCcw className="h-3.5 w-3.5" />
            Discard edits
          </button>
          {dirty && <span className="text-xs font-medium text-amber-700">Unsaved changes</span>}
        </div>
      </div>
      <ToastContainer toasts={toasts} onClose={hideToast} />
    </>
  );
}
