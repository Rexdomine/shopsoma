import { useState, useEffect, useRef } from 'react';
import {
  Save,
  DollarSign,
  Loader2,
  Database,
  RefreshCw,
  Truck,
  WalletCards,
  Percent,
  ListChecks,
} from 'lucide-react';
import ManualShippingSettings from '../../components/admin/ManualShippingSettings';
import type { ShippingProviderSettings } from '../../services/settingsService';
import AdminSidebar from '../../components/admin/AdminSidebar';
import {
  getExchangeRate,
  updateExchangeRate,
  getShippingProviderSettings,
  updateShippingProviderSettings,
  getPayoutHoldSettings,
  updatePayoutHoldSettings,
  getCommissionSettings,
  updateCommissionSettings,
  getAdminFeaturedRotationSettings,
  updateFeaturedRotationSettings,
  syncRenderDatabase,
  type ExchangeRate,
  type PayoutHoldSettings,
  type CommissionSettings,
  type FeaturedRotationSettings,
} from '../../services/settingsService';
import { useToast } from '../../hooks/useToast';
import ToastContainer from '../../components/ui/ToastContainer';
import { useCurrency } from '../../hooks/useCurrency';

export default function AdminSettings() {
  const { toasts, hideToast, success, error } = useToast();
  const { fetchExchangeRate } = useCurrency();

  const [exchangeRate, setExchangeRate] = useState<ExchangeRate | null>(null);
  const [rateInput, setRateInput] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [hasChanges, setHasChanges] = useState(false);

  // ShipBubble settings state
  const [shippingProvider, setShippingProvider] = useState<ShippingProviderSettings | null>(null);
  const [savingShipping, setSavingShipping] = useState(false);
  const [payoutHold, setPayoutHold] = useState<PayoutHoldSettings | null>(null);
  const [payoutHoldInput, setPayoutHoldInput] = useState('');
  const [savingPayoutHold, setSavingPayoutHold] = useState(false);
  const [payoutHoldChanged, setPayoutHoldChanged] = useState(false);
  const [commissionSettings, setCommissionSettings] = useState<CommissionSettings | null>(null);
  const [commissionInput, setCommissionInput] = useState('');
  const [savingCommission, setSavingCommission] = useState(false);
  const [commissionChanged, setCommissionChanged] = useState(false);
  const [applyCommissionToExisting, setApplyCommissionToExisting] = useState(false);
  const [featuredRotation, setFeaturedRotation] = useState<FeaturedRotationSettings | null>(null);
  const [featuredRotationInput, setFeaturedRotationInput] = useState('');
  const [savingFeaturedRotation, setSavingFeaturedRotation] = useState(false);
  const [featuredRotationChanged, setFeaturedRotationChanged] = useState(false);
  const [syncingDb, setSyncingDb] = useState(false);
  const [lastDbSync, setLastDbSync] = useState<string | null>(null);
  const [syncProgress, setSyncProgress] = useState(0);
  const [syncStatus, setSyncStatus] = useState<'idle' | 'running' | 'success' | 'error'>('idle');
  const settingsCategories = ['currency', 'shipping', 'rates', 'payout', 'commission', 'featured', 'database'] as const;
  const categoryFromHash = () => {
    const value = window.location.hash.replace(/^#/, '');
    return settingsCategories.includes(value as typeof settingsCategories[number]) ? value : 'currency';
  };
  const [category, setCategory] = useState(categoryFromHash);
  const [manualRatesDirty, setManualRatesDirty] = useState(false);
  const discardManualRatesRef = useRef<(() => void) | null>(null);
  const syncTimerRef = useRef<number | null>(null);
  const switchCategoryRef = useRef<(next: string, writeHistory?: boolean) => void>(() => undefined);

  useEffect(() => {
    fetchSettings();
  }, []);

  useEffect(() => {
    const syncCategory = () => switchCategoryRef.current(categoryFromHash(), false);
    window.addEventListener('hashchange', syncCategory);
    window.addEventListener('popstate', syncCategory);
    return () => {
      window.removeEventListener('hashchange', syncCategory);
      window.removeEventListener('popstate', syncCategory);
    };
  }, []);

  useEffect(() => {
    return () => {
      if (syncTimerRef.current !== null) {
        window.clearInterval(syncTimerRef.current);
      }
    };
  }, []);

  const fetchSettings = async () => {
    try {
      setLoading(true);
      const [rate, shipping, hold, commission, rotation] = await Promise.all([
        getExchangeRate(),
        getShippingProviderSettings(),
        getPayoutHoldSettings(),
        getCommissionSettings(),
        getAdminFeaturedRotationSettings(),
      ]);
      setExchangeRate(rate);
      setRateInput(rate.rate.toString());
      setShippingProvider(shipping);
      setPayoutHold(hold);
      setPayoutHoldInput(hold.hold_days.toString());
      setCommissionSettings(commission);
      setCommissionInput(commission.commission_rate.toString());
      setApplyCommissionToExisting(false);
      setFeaturedRotation(rotation);
      setFeaturedRotationInput(rotation.rotation_minutes.toString());
    } catch (err: any) {
      console.error('Failed to fetch settings:', err);
      error(err.response?.data?.detail || 'Failed to load settings', 'Error');
    } finally {
      setLoading(false);
    }
  };

  const handleRateChange = (value: string) => {
    setRateInput(value);
    const numValue = parseFloat(value);
    setHasChanges(exchangeRate ? value.trim() === '' || Number.isNaN(numValue) || numValue !== exchangeRate.rate : value.trim() !== '');
  };

  const handleSaveRate = async () => {
    const numValue = parseFloat(rateInput);

    // Validation
    if (isNaN(numValue) || numValue <= 0) {
      error('Please enter a valid exchange rate greater than 0', 'Invalid Input');
      return;
    }

    if (numValue < 100 || numValue > 10000) {
      error('Exchange rate must be between 100 and 10,000 NGN per USD', 'Invalid Range');
      return;
    }

    try {
      setSaving(true);
      const updatedRate = await updateExchangeRate(numValue);
      setExchangeRate(updatedRate);
      setRateInput(updatedRate.rate.toString());
      setHasChanges(false);

      // Update the currency store with new rate
      await fetchExchangeRate();

      success('Exchange rate updated successfully', 'Success');
    } catch (err: any) {
      console.error('Failed to update exchange rate:', err);
      error(
        err.response?.data?.detail || 'Failed to update exchange rate',
        'Error'
      );
    } finally {
      setSaving(false);
    }
  };

  const handleReset = () => {
    if (exchangeRate) {
      setRateInput(exchangeRate.rate.toString());
      setHasChanges(false);
    }
  };

  const handleShippingProvider = async (provider: ShippingProviderSettings['provider']) => {
    try {
      setSavingShipping(true);
      const updated = await updateShippingProviderSettings(provider);
      setShippingProvider(updated);
      success(
        `Shipping provider saved: ${updated.provider}`,
        'Success'
      );
    } catch (err: any) {
      console.error('Failed to update shipping provider:', err);
      error(
        err.response?.data?.detail || 'Failed to update shipping provider',
        'Error'
      );
    } finally {
      setSavingShipping(false);
    }
  };

  const handlePayoutHoldChange = (value: string) => {
    setPayoutHoldInput(value);
    setPayoutHoldChanged(payoutHold ? value !== payoutHold.hold_days.toString() : value !== '');
  };

  const handleSavePayoutHold = async () => {
    const parsed = Number(payoutHoldInput);
    if (Number.isNaN(parsed) || parsed < 0 || parsed > 3650) {
      error('Payout hold days must be between 0 and 3650', 'Invalid Input');
      return;
    }

    try {
      setSavingPayoutHold(true);
      const updated = await updatePayoutHoldSettings(parsed);
      setPayoutHold(updated);
      setPayoutHoldInput(updated.hold_days.toString());
      setPayoutHoldChanged(false);
      success('Payout hold updated successfully', 'Success');
    } catch (err: any) {
      console.error('Failed to update payout hold:', err);
      error(err.response?.data?.detail || 'Failed to update payout hold', 'Error');
    } finally {
      setSavingPayoutHold(false);
    }
  };

  const handleResetPayoutHold = () => {
    if (payoutHold) {
      setPayoutHoldInput(payoutHold.hold_days.toString());
      setPayoutHoldChanged(false);
    }
  };

  const handleCommissionChange = (value: string) => {
    setCommissionInput(value);
    setCommissionChanged(commissionSettings ? value !== commissionSettings.commission_rate.toString() : value !== '');
  };

  const handleSaveCommission = async () => {
    const parsed = Number(commissionInput);
    if (Number.isNaN(parsed) || parsed < 0 || parsed > 100) {
      error('Commission percentage must be between 0 and 100', 'Invalid Input');
      return;
    }

    try {
      setSavingCommission(true);
      const updated = await updateCommissionSettings(parsed, applyCommissionToExisting);
      setCommissionSettings(updated);
      setCommissionInput(updated.commission_rate.toString());
      setApplyCommissionToExisting(false);
      setCommissionChanged(false);
      success('Commission settings updated successfully', 'Success');
    } catch (err: unknown) {
      console.error('Failed to update commission settings:', err);
      const detail = typeof err === 'object' && err !== null && 'response' in err
        ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
        : undefined;
      error(detail || 'Failed to update commission settings', 'Error');
    } finally {
      setSavingCommission(false);
    }
  };

  const handleResetCommission = () => {
    if (commissionSettings) {
      setCommissionInput(commissionSettings.commission_rate.toString());
      setApplyCommissionToExisting(false);
      setCommissionChanged(false);
    }
  };

  const handleFeaturedRotationChange = (value: string) => {
    setFeaturedRotationInput(value);
    const parsed = Number(value);
    if (!Number.isNaN(parsed) && featuredRotation) {
      setFeaturedRotationChanged(parsed !== featuredRotation.rotation_minutes);
    }
  };

  const handleSaveFeaturedRotation = async () => {
    const parsed = Number(featuredRotationInput);
    if (Number.isNaN(parsed) || parsed < 1 || parsed > 1440) {
      error('Rotation interval must be between 1 and 1440 minutes', 'Invalid Input');
      return;
    }

    try {
      setSavingFeaturedRotation(true);
      const updated = await updateFeaturedRotationSettings(parsed);
      setFeaturedRotation(updated);
      setFeaturedRotationInput(updated.rotation_minutes.toString());
      setFeaturedRotationChanged(false);
      success('Featured rotation updated successfully', 'Success');
    } catch (err: any) {
      console.error('Failed to update featured rotation:', err);
      error(err.response?.data?.detail || 'Failed to update featured rotation', 'Error');
    } finally {
      setSavingFeaturedRotation(false);
    }
  };

  const handleResetFeaturedRotation = () => {
    if (featuredRotation) {
      setFeaturedRotationInput(featuredRotation.rotation_minutes.toString());
      setFeaturedRotationChanged(false);
    }
  };

  const handleDbSync = async () => {
    const confirmed = window.confirm(
      'This will replace your local database with the latest data from Render. Continue?'
    );
    if (!confirmed) {
      return;
    }

    if (syncTimerRef.current !== null) {
      window.clearInterval(syncTimerRef.current);
    }

    try {
      setSyncingDb(true);
      setSyncStatus('running');
      setSyncProgress(5);
      syncTimerRef.current = window.setInterval(() => {
        setSyncProgress((prev) => {
          if (prev >= 90) {
            return prev;
          }
          const step = Math.max(2, Math.floor(Math.random() * 8));
          return Math.min(90, prev + step);
        });
      }, 700);

      const result = await syncRenderDatabase();
      setLastDbSync(result.message);
      setSyncStatus('success');
      setSyncProgress(100);
      success(result.message, 'Database Sync Complete');
    } catch (err: any) {
      console.error('Failed to sync database:', err);
      error(err.response?.data?.detail || 'Database sync failed', 'Error');
      setSyncStatus('error');
    } finally {
      if (syncTimerRef.current !== null) {
        window.clearInterval(syncTimerRef.current);
        syncTimerRef.current = null;
      }
      setSyncingDb(false);
      window.setTimeout(() => {
        setSyncProgress(0);
        setSyncStatus('idle');
      }, 1500);
    }
  };

  if (loading) {
    return (
      <div className="flex min-h-screen bg-[var(--color-page-bg)]">
        <div className="hidden md:flex">
          <AdminSidebar activePrimary="settings" />
        </div>
        <div className="flex-1 flex items-center justify-center">
          <div className="flex items-center gap-3 text-gray-600">
            <Loader2 className="h-6 w-6 animate-spin" />
            <span>Loading settings...</span>
          </div>
        </div>
      </div>
    );
  }

  const dhlReadyForCheckout = Boolean(shippingProvider?.readiness.dhl && shippingProvider?.checkout_estimates_required);
  const categories = [
    ['currency', 'Currency', 'Exchange rates and display values', DollarSign],
    ['shipping', 'Shipping', 'Provider and checkout readiness', Truck],
    ['rates', 'Manual rates', 'Destination-based delivery pricing', ListChecks],
    ['payout', 'Payouts', 'Hold periods and settlement rules', WalletCards],
    ['commission', 'Commission', 'Vendor defaults and future orders', Percent],
    ['featured', 'Featured', 'Homepage rotation timing', RefreshCw],
    ['database', 'Database', 'Local-only development tools', Database],
  ] as const;
  const dirty = hasChanges || payoutHoldChanged || commissionChanged || applyCommissionToExisting || featuredRotationChanged || manualRatesDirty;
  const savingAny = saving || savingShipping || savingPayoutHold || savingCommission || savingFeaturedRotation;
  const Summary = ({ title, value, detail }: { title: string; value: string; detail: string }) => (
    <div className="rounded-xl border border-slate-200 bg-slate-50 p-4"><p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{title}</p><p className="mt-2 text-xl font-semibold text-slate-950">{value}</p><p className="mt-1 text-xs text-slate-500">{detail}</p></div>
  );
  const saveBar = (onSave: () => void, onReset: () => void, changed: boolean, busy: boolean) => <div className="flex flex-wrap items-center gap-3 border-t border-slate-100 pt-5"><button type="button" onClick={onSave} disabled={!changed || busy} className="inline-flex items-center gap-2 rounded-lg bg-[#105E53] px-4 py-2.5 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40"><Save className="h-4 w-4" />{busy ? 'Saving…' : 'Save changes'}</button><button type="button" onClick={onReset} disabled={!changed || busy} className="rounded-lg border border-slate-300 px-4 py-2.5 text-sm font-semibold text-slate-700 disabled:opacity-40">Discard edits</button>{changed && <span className="text-xs font-medium text-amber-700">Unsaved changes</span>}</div>;
  const switchCategory = (next: string, writeHistory = true) => {
    if (next === category) return;
    if (savingAny) {
      error('Please wait for the current save to finish before switching categories.', 'Save in progress');
      return;
    }
    if (dirty && !window.confirm('You have unsaved edits. Switch category and discard them?')) return;
    handleReset();
    handleResetPayoutHold();
    handleResetCommission();
    handleResetFeaturedRotation();
    discardManualRatesRef.current?.();
    setManualRatesDirty(false);
    if (writeHistory && settingsCategories.includes(next as typeof settingsCategories[number])) {
      window.history.pushState(null, '', `#${next}`);
    }
    setCategory(next);
  };
  switchCategoryRef.current = switchCategory;
  return <div className="flex min-h-screen bg-[var(--color-page-bg)]"><div className="hidden md:flex"><AdminSidebar activePrimary="settings" /></div><main className="min-w-0 flex-1"><div className="mx-auto max-w-[1280px] px-4 py-6 sm:px-6 lg:px-10 lg:py-10">
    <header className="mb-8"><p className="text-xs font-bold uppercase tracking-[0.18em] text-[#105E53]">ShopSoma admin</p><div className="mt-2 flex flex-col justify-between gap-4 sm:flex-row sm:items-end"><div><h1 className="text-3xl font-semibold tracking-tight text-slate-950">Settings</h1><p className="mt-2 max-w-2xl text-sm text-slate-600">One focused workspace at a time. Review the current value first, then make a deliberate change.</p></div>{dirty && <div className="rounded-full bg-amber-50 px-3 py-1.5 text-xs font-semibold text-amber-800">Draft edits pending</div>}</div></header>
    <div className="grid gap-6 lg:grid-cols-[250px_minmax(0,1fr)]"><nav aria-label="Settings categories" className="h-fit rounded-2xl border border-slate-200 bg-white p-2 shadow-sm lg:sticky lg:top-6"><p className="px-3 pb-2 pt-2 text-[11px] font-bold uppercase tracking-[0.16em] text-slate-400">Configuration</p>{categories.map(([id,label,desc,Icon]) => <button key={id} type="button" onClick={() => switchCategory(id)} aria-current={category === id ? 'page' : undefined} className={`flex w-full items-start gap-3 rounded-xl px-3 py-3 text-left transition ${category === id ? 'bg-[#E7F3EF] text-[#105E53]' : 'text-slate-600 hover:bg-slate-50'}`}><Icon className="mt-0.5 h-4 w-4 shrink-0" /><span><span className="block text-sm font-semibold">{label}</span><span className="mt-0.5 block text-xs leading-4 opacity-70">{desc}</span></span></button>)}</nav>
    <section aria-live="polite" className="min-w-0">{category === 'currency' && <div className="space-y-5"><div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-7"><div className="mb-6 flex flex-wrap items-start justify-between gap-4"><div><p className="text-xs font-bold uppercase tracking-[0.16em] text-[#105E53]">Currency</p><h2 className="mt-1 text-2xl font-semibold text-slate-950">Exchange rate</h2><p className="mt-1 text-sm text-slate-600">Controls how NGN prices are represented in USD across the storefront.</p></div>{exchangeRate && <Summary title="Current value" value={`₦${exchangeRate.rate.toLocaleString('en-NG', { minimumFractionDigits: 2 })}`} detail="per 1 USD" />}</div><label htmlFor="exchange-rate" className="block max-w-sm text-sm font-semibold text-slate-800">USD to NGN<input id="exchange-rate" type="number" min="100" max="10000" step="0.01" value={rateInput} onChange={e => handleRateChange(e.target.value)} className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-2.5 text-slate-900" /><span className="mt-1 block text-xs font-normal text-slate-500">Allowed range: 100–10,000 NGN. Changes apply immediately after saving.</span></label>{saveBar(handleSaveRate, handleReset, hasChanges, saving)}</div></div>}
    {category === 'shipping' && <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-7"><p className="text-xs font-bold uppercase tracking-[0.16em] text-[#105E53]">Fulfilment</p><h2 className="mt-1 text-2xl font-semibold text-slate-950">Shipping provider</h2><p className="mt-1 text-sm text-slate-600">Choose the provider used for checkout estimates. Availability and readiness gates remain enforced by the existing service.</p><div className="mt-7 grid gap-4 sm:grid-cols-2"><label className="text-sm font-semibold text-slate-800">Active provider<select aria-label="Shipping provider" value={shippingProvider?.provider ?? ''} disabled={savingShipping || !shippingProvider} onChange={e => handleShippingProvider(e.target.value as ShippingProviderSettings['provider'])} className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-2.5"><option value="manual">Manual rates</option><option value="shipbubble" disabled={!shippingProvider?.readiness.shipbubble}>ShipBubble — unavailable for secure checkout</option><option value="dhl" disabled={!dhlReadyForCheckout}>DHL</option></select></label><div className="rounded-xl border border-slate-200 bg-slate-50 p-4"><p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Checkout readiness</p><p className={`mt-2 text-sm font-semibold ${dhlReadyForCheckout ? 'text-emerald-700' : 'text-slate-700'}`}>{dhlReadyForCheckout ? 'DHL estimates enabled' : 'Provider gate active'}</p><p className="mt-1 text-xs text-slate-500">Provider activation and credentials are not changed here.</p></div></div></div>}
    {category === 'rates' && <ManualShippingSettings onDirtyChange={setManualRatesDirty} onDiscard={clear => { discardManualRatesRef.current = clear; }} />}
    {category === 'payout' && <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-7"><p className="text-xs font-bold uppercase tracking-[0.16em] text-[#105E53]">Settlements</p><h2 className="mt-1 text-2xl font-semibold text-slate-950">Payout hold</h2><p className="mt-1 text-sm text-slate-600">Keep vendor funds on hold for the configured number of days before payout eligibility.</p>{payoutHold && <div className="mt-6 mb-6"><Summary title="Current value" value={`${payoutHold.hold_days} days`} detail="applies to future payout eligibility" /></div>}<label className="block max-w-sm text-sm font-semibold">Hold duration<input type="number" min="0" max="3650" value={payoutHoldInput} onChange={e => handlePayoutHoldChange(e.target.value)} className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-2.5" /><span className="mt-1 block text-xs font-normal text-slate-500">Allowed range: 0–3,650 days.</span></label>{saveBar(handleSavePayoutHold, handleResetPayoutHold, payoutHoldChanged, savingPayoutHold)}</div>}
    {category === 'commission' && <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-7"><p className="text-xs font-bold uppercase tracking-[0.16em] text-[#105E53]">Vendor economics</p><h2 className="mt-1 text-2xl font-semibold text-slate-950">Commission default</h2><p className="mt-1 text-sm text-slate-600">Set the default percentage for new vendors without changing historical order math.</p>{commissionSettings && <div className="mt-6 mb-6"><Summary title="Current value" value={`${commissionSettings.commission_rate}%`} detail="default commission" /></div>}<label className="block max-w-sm text-sm font-semibold">Commission percentage<input type="number" min="0" max="100" value={commissionInput} onChange={e => handleCommissionChange(e.target.value)} className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-2.5" /></label><label className="mt-5 flex max-w-xl gap-3 text-sm text-slate-600"><input type="checkbox" checked={applyCommissionToExisting} onChange={e => setApplyCommissionToExisting(e.target.checked)} className="mt-1" />Also update existing vendor defaults for future orders.</label>{saveBar(handleSaveCommission, handleResetCommission, commissionChanged || applyCommissionToExisting, savingCommission)}</div>}
    {category === 'featured' && <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-7"><p className="text-xs font-bold uppercase tracking-[0.16em] text-[#105E53]">Storefront curation</p><h2 className="mt-1 text-2xl font-semibold text-slate-950">Featured rotation</h2><p className="mt-1 text-sm text-slate-600">Control how often the homepage featured selection changes.</p>{featuredRotation && <div className="mt-6 mb-6"><Summary title="Current value" value={`${featuredRotation.rotation_minutes} minutes`} detail="between automatic rotations" /></div>}<label className="block max-w-sm text-sm font-semibold">Rotation interval<input type="number" min="1" max="1440" value={featuredRotationInput} onChange={e => handleFeaturedRotationChange(e.target.value)} className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-2.5" /><span className="mt-1 block text-xs font-normal text-slate-500">Allowed range: 1–1,440 minutes.</span></label>{saveBar(handleSaveFeaturedRotation, handleResetFeaturedRotation, featuredRotationChanged, savingFeaturedRotation)}</div>}
    {category === 'database' && <div className="rounded-2xl border border-amber-200 bg-white p-5 shadow-sm sm:p-7"><p className="text-xs font-bold uppercase tracking-[0.16em] text-amber-700">Developer tools</p><h2 className="mt-1 text-2xl font-semibold text-slate-950">Local database sync</h2><p className="mt-1 text-sm text-slate-600">This destructive action is intentionally available only in local development. It never runs against hosted environments.</p><div className="mt-6 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900"><strong>Local-only gate.</strong> Syncing replaces local data with Render staging data.</div><button type="button" onClick={handleDbSync} disabled={syncingDb} className="mt-6 inline-flex items-center gap-2 rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-50"><RefreshCw className="h-4 w-4" />{syncingDb ? 'Syncing…' : 'Sync Render to Local'}</button>{lastDbSync && <p className="mt-4 text-sm text-slate-600">{lastDbSync}</p>}{syncStatus === 'running' && <p className="mt-2 text-xs text-slate-500">Sync progress: {syncProgress}%</p>}</div>}
    </section></div></div></main><ToastContainer toasts={toasts} onClose={hideToast} /></div>;
}
