import { useState, useEffect, useRef } from 'react';
import {
  Save,
  DollarSign,
  Loader2,
  AlertCircle,
  Database,
  RefreshCw,
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
  const syncTimerRef = useRef<number | null>(null);

  useEffect(() => {
    fetchSettings();
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
    if (!isNaN(numValue) && exchangeRate) {
      setHasChanges(numValue !== exchangeRate.rate);
    }
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
    const parsed = Number(value);
    if (!Number.isNaN(parsed) && payoutHold) {
      setPayoutHoldChanged(parsed !== payoutHold.hold_days);
    }
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
    const parsed = Number(value);
    if (!Number.isNaN(parsed) && commissionSettings) {
      setCommissionChanged(parsed !== commissionSettings.commission_rate);
    }
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
        <AdminSidebar activePrimary="settings" />
        <div className="flex-1 flex items-center justify-center">
          <div className="flex items-center gap-3 text-gray-600">
            <Loader2 className="h-6 w-6 animate-spin" />
            <span>Loading settings...</span>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen bg-[var(--color-page-bg)]">
      <AdminSidebar activePrimary="settings" />

      <div className="flex-1 overflow-auto">
        <div className="px-8 py-8 space-y-6">
          {/* Header */}
          <div>
            <h1 className="text-2xl font-semibold text-gray-900">Settings</h1>
            <p className="text-sm text-gray-600 mt-1">
              Manage application settings and configurations
            </p>
          </div>

          {/* Currency Settings Card */}
          <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
            <div className="border-b border-gray-200 px-6 py-4">
              <div className="flex items-center gap-3">
                <div className="h-10 w-10 rounded-xl bg-[#0B1D2C] text-white flex items-center justify-center">
                  <DollarSign className="w-5 h-5" />
                </div>
                <div>
                  <h2 className="text-lg font-semibold text-gray-900">Currency Settings</h2>
                  <p className="text-sm text-gray-600">Manage exchange rates for currency conversion</p>
                </div>
              </div>
            </div>

            <div className="p-6 space-y-6">
              {/* Exchange Rate Input */}
              <div>
                <label htmlFor="exchange-rate" className="block text-sm font-medium text-gray-700 mb-2">
                  USD to NGN Exchange Rate
                  <span className="text-gray-500 font-normal ml-2">(1 USD = X NGN)</span>
                </label>
                <div className="flex items-start gap-4">
                  <div className="flex-1 max-w-md">
                    <div className="relative">
                      <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500 font-medium">
                        ₦
                      </span>
                      <input
                        id="exchange-rate"
                        type="number"
                        min="100"
                        max="10000"
                        step="0.01"
                        value={rateInput}
                        onChange={(e) => handleRateChange(e.target.value)}
                        className="w-full pl-8 pr-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-[#105E53] focus:border-transparent text-gray-900"
                        placeholder="Enter exchange rate"
                      />
                    </div>
                    <p className="text-xs text-gray-500 mt-2">
                      Valid range: 100 - 10,000 NGN per USD
                    </p>
                  </div>

                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={handleReset}
                      disabled={!hasChanges || saving}
                      className="px-4 py-2.5 border border-gray-300 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      Reset
                    </button>
                    <button
                      type="button"
                      onClick={handleSaveRate}
                      disabled={!hasChanges || saving}
                      className="px-4 py-2.5 bg-[#105E53] text-white rounded-lg text-sm font-medium hover:bg-[#0d4a42] transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                    >
                      {saving ? (
                        <>
                          <Loader2 className="w-4 h-4 animate-spin" />
                          Saving...
                        </>
                      ) : (
                        <>
                          <Save className="w-4 h-4" />
                          Save Changes
                        </>
                      )}
                    </button>
                  </div>
                </div>
              </div>

              {/* Current Rate Display */}
              {exchangeRate && (
                <div className="bg-gray-50 rounded-lg p-4 border border-gray-200">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-sm font-medium text-gray-700">Current Exchange Rate</p>
                      <p className="text-2xl font-semibold text-[#0B1D2C] mt-1">
                        1 USD = ₦{exchangeRate.rate.toLocaleString('en-NG', {
                          minimumFractionDigits: 2,
                          maximumFractionDigits: 2
                        })}
                      </p>
                    </div>
                    <div className="text-right">
                      <p className="text-xs text-gray-500">Last Updated</p>
                      <p className="text-sm text-gray-700 mt-0.5">
                        {new Date(exchangeRate.updated_at).toLocaleString('en-US', {
                          dateStyle: 'medium',
                          timeStyle: 'short'
                        })}
                      </p>
                    </div>
                  </div>
                </div>
              )}

              {/* Info Box */}
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                <div className="flex items-start gap-3">
                  <AlertCircle className="w-5 h-5 text-blue-600 mt-0.5 flex-shrink-0" />
                  <div>
                    <p className="text-sm font-semibold text-blue-900 mb-1">About Exchange Rates</p>
                    <ul className="text-sm text-blue-800 space-y-1">
                      <li>• All product prices are stored in NGN (Nigerian Naira)</li>
                      <li>• The exchange rate is used to convert prices to USD for display</li>
                      <li>• Changes take effect immediately across the platform</li>
                      <li>• Update regularly to reflect current market rates</li>
                    </ul>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <section className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6 space-y-4">
            <h2 className="text-lg font-semibold">Shipping Provider</h2>
            <label className="block">Current provider
              <select aria-label="Shipping provider" value={shippingProvider?.provider ?? ''} disabled={savingShipping || !shippingProvider}
                onChange={event => void handleShippingProvider(event.target.value as ShippingProviderSettings['provider'])}
                className="block mt-2 rounded-lg border border-gray-300 p-2">
                {!shippingProvider && <option value="">Loading…</option>}
                <option value="manual">Manual rates</option>
                <option value="shipbubble" disabled={!shippingProvider?.readiness.shipbubble}>ShipBubble — unavailable for secure checkout</option>
                <option value="dhl" disabled={!shippingProvider?.readiness.dhl}>DHL — {shippingProvider?.readiness.dhl ? 'sandbox ready' : 'pending / not enabled'}</option>
              </select>
            </label>
            {savingShipping && <p role="status">Saving provider…</p>}
            <p className="text-sm text-gray-600">Manual rates make no carrier calls. DHL remains subject to existing sandbox gates. Provider changes apply to new quotes; issued quotes and payment recovery keep their saved terms.</p>
          </section>
          <ManualShippingSettings />

          {/* Payout Hold Settings Card */}
          <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
            <div className="border-b border-gray-200 px-6 py-4">
              <div className="flex items-center gap-3">
                <div className="h-10 w-10 rounded-xl bg-[#0B1D2C] text-white flex items-center justify-center">
                  <DollarSign className="w-5 h-5" />
                </div>
                <div>
                  <h2 className="text-lg font-semibold text-gray-900">Payout Hold</h2>
                  <p className="text-sm text-gray-600">Set how long vendors wait before withdrawing</p>
                </div>
              </div>
            </div>

            <div className="p-6 space-y-6">
              <div>
                <label htmlFor="payout-hold" className="block text-sm font-medium text-gray-700 mb-2">
                  Hold period (days)
                </label>
                <div className="flex items-start gap-4">
                  <div className="flex-1 max-w-md">
                    <input
                      id="payout-hold"
                      type="number"
                      min="0"
                      max="3650"
                      step="1"
                      value={payoutHoldInput}
                      onChange={(event) => handlePayoutHoldChange(event.target.value)}
                      className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-[#105E53] focus:border-transparent text-gray-900"
                      placeholder="Enter hold days"
                    />
                    <p className="text-xs text-gray-500 mt-2">
                      Set to 0 for no hold. Max 3650 days.
                    </p>
                  </div>

                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={handleResetPayoutHold}
                      disabled={!payoutHoldChanged || savingPayoutHold}
                      className="px-4 py-2.5 border border-gray-300 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      Reset
                    </button>
                    <button
                      type="button"
                      onClick={handleSavePayoutHold}
                      disabled={!payoutHoldChanged || savingPayoutHold}
                      className="px-4 py-2.5 bg-[#105E53] text-white rounded-lg text-sm font-medium hover:bg-[#0d4a42] transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                    >
                      {savingPayoutHold ? (
                        <>
                          <Loader2 className="w-4 h-4 animate-spin" />
                          Saving...
                        </>
                      ) : (
                        <>
                          <Save className="w-4 h-4" />
                          Save Changes
                        </>
                      )}
                    </button>
                  </div>
                </div>
              </div>

              {payoutHold && (
                <div className="bg-gray-50 rounded-lg p-4 border border-gray-200">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-sm font-medium text-gray-700">Current Hold Period</p>
                      <p className="text-2xl font-semibold text-[#0B1D2C] mt-1">
                        {payoutHold.hold_days} day{payoutHold.hold_days === 1 ? '' : 's'}
                      </p>
                    </div>
                    <div className="text-right">
                      <p className="text-xs text-gray-500">Last Updated</p>
                      <p className="text-sm text-gray-700 mt-0.5">
                        {payoutHold.updated_at
                          ? new Date(payoutHold.updated_at).toLocaleString('en-US', {
                              dateStyle: 'medium',
                              timeStyle: 'short'
                            })
                          : 'Not set'}
                      </p>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Commission Settings Card */}
          <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
            <div className="border-b border-gray-200 px-6 py-4">
              <div className="flex items-center gap-3">
                <div className="h-10 w-10 rounded-xl bg-[#105E53] text-white flex items-center justify-center">
                  <DollarSign className="w-5 h-5" />
                </div>
                <div>
                  <h2 className="text-lg font-semibold text-gray-900">Commission</h2>
                  <p className="text-sm text-gray-600">Control default vendor commission for future order calculations</p>
                </div>
              </div>
            </div>

            <div className="p-6 space-y-6">
              <div>
                <label htmlFor="commission-rate" className="block text-sm font-medium text-gray-700 mb-2">
                  Default commission percentage
                </label>
                <div className="flex items-start gap-4">
                  <div className="flex-1 max-w-md">
                    <div className="relative">
                      <input
                        id="commission-rate"
                        type="number"
                        min="0"
                        max="100"
                        step="0.01"
                        value={commissionInput}
                        onChange={(event) => handleCommissionChange(event.target.value)}
                        className="w-full pr-10 px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-[#105E53] focus:border-transparent text-gray-900"
                        placeholder="Enter commission percentage"
                      />
                      <span className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 font-medium">
                        %
                      </span>
                    </div>
                    <p className="text-xs text-gray-500 mt-2">
                      New orders snapshot the vendor commission at order creation. Old orders and payouts are not changed.
                    </p>
                    <label className="mt-4 flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
                      <input
                        type="checkbox"
                        checked={applyCommissionToExisting}
                        onChange={(event) => setApplyCommissionToExisting(event.target.checked)}
                        className="mt-1 h-4 w-4 rounded border-amber-300 text-[#105E53] focus:ring-[#105E53]"
                      />
                      <span>
                        Also update existing vendor commission rates for future orders. Leave unchecked to apply this only as the default for newly created vendors.
                      </span>
                    </label>
                  </div>

                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={handleResetCommission}
                      disabled={(!commissionChanged && !applyCommissionToExisting) || savingCommission}
                      className="px-4 py-2.5 border border-gray-300 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      Reset
                    </button>
                    <button
                      type="button"
                      onClick={handleSaveCommission}
                      disabled={(!commissionChanged && !applyCommissionToExisting) || savingCommission}
                      className="px-4 py-2.5 bg-[#105E53] text-white rounded-lg text-sm font-medium hover:bg-[#0d4a42] transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                    >
                      {savingCommission ? (
                        <>
                          <Loader2 className="w-4 h-4 animate-spin" />
                          Saving...
                        </>
                      ) : (
                        <>
                          <Save className="w-4 h-4" />
                          Save Changes
                        </>
                      )}
                    </button>
                  </div>
                </div>
              </div>

              {commissionSettings && (
                <div className="bg-gray-50 rounded-lg p-4 border border-gray-200">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-sm font-medium text-gray-700">Current Default Commission</p>
                      <p className="text-2xl font-semibold text-[#0B1D2C] mt-1">
                        {commissionSettings.commission_rate.toLocaleString('en-US', {
                          minimumFractionDigits: 0,
                          maximumFractionDigits: 2
                        })}%
                      </p>
                    </div>
                    <div className="text-right">
                      <p className="text-xs text-gray-500">Last Updated</p>
                      <p className="text-sm text-gray-700 mt-0.5">
                        {commissionSettings.updated_at
                          ? new Date(commissionSettings.updated_at).toLocaleString('en-US', {
                              dateStyle: 'medium',
                              timeStyle: 'short'
                            })
                          : 'Not set'}
                      </p>
                    </div>
                  </div>
                </div>
              )}

              <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                <div className="flex items-start gap-3">
                  <AlertCircle className="w-5 h-5 text-blue-600 mt-0.5 flex-shrink-0" />
                  <div>
                    <p className="text-sm font-semibold text-blue-900 mb-1">About Commission</p>
                    <ul className="text-sm text-blue-800 space-y-1">
                      <li>• Vendor-level commission rates are used for new order item snapshots</li>
                      <li>• Historical order and payout records keep their original commission math</li>
                      <li>• Use the checkbox only when the new percentage should apply to existing vendors going forward</li>
                    </ul>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Featured Rotation Settings Card */}
          <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
            <div className="border-b border-gray-200 px-6 py-4">
              <div className="flex items-center gap-3">
                <div className="h-10 w-10 rounded-xl bg-[#105E53] text-white flex items-center justify-center">
                  <RefreshCw className="w-5 h-5" />
                </div>
                <div>
                  <h2 className="text-lg font-semibold text-gray-900">Featured Rotation</h2>
                  <p className="text-sm text-gray-600">Control how often the homepage feature changes</p>
                </div>
              </div>
            </div>

            <div className="p-6 space-y-6">
              <div>
                <label htmlFor="featured-rotation" className="block text-sm font-medium text-gray-700 mb-2">
                  Rotation interval (minutes)
                </label>
                <div className="flex items-start gap-4">
                  <div className="flex-1 max-w-md">
                    <input
                      id="featured-rotation"
                      type="number"
                      min="1"
                      max="1440"
                      step="1"
                      value={featuredRotationInput}
                      onChange={(event) => handleFeaturedRotationChange(event.target.value)}
                      className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-[#105E53] focus:border-transparent text-gray-900"
                      placeholder="Enter minutes"
                    />
                    <p className="text-xs text-gray-500 mt-2">
                      Set between 1 and 1440 minutes (24 hours).
                    </p>
                  </div>

                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={handleResetFeaturedRotation}
                      disabled={!featuredRotationChanged || savingFeaturedRotation}
                      className="px-4 py-2.5 border border-gray-300 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      Reset
                    </button>
                    <button
                      type="button"
                      onClick={handleSaveFeaturedRotation}
                      disabled={!featuredRotationChanged || savingFeaturedRotation}
                      className="px-4 py-2.5 bg-[#105E53] text-white rounded-lg text-sm font-medium hover:bg-[#0d4a42] transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                    >
                      {savingFeaturedRotation ? (
                        <>
                          <Loader2 className="w-4 h-4 animate-spin" />
                          Saving...
                        </>
                      ) : (
                        <>
                          <Save className="w-4 h-4" />
                          Save Changes
                        </>
                      )}
                    </button>
                  </div>
                </div>
              </div>

              {featuredRotation && (
                <div className="bg-gray-50 rounded-lg p-4 border border-gray-200">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-sm font-medium text-gray-700">Current Rotation Interval</p>
                      <p className="text-2xl font-semibold text-[#0B1D2C] mt-1">
                        {featuredRotation.rotation_minutes} minute{featuredRotation.rotation_minutes === 1 ? '' : 's'}
                      </p>
                    </div>
                    <div className="text-right">
                      <p className="text-xs text-gray-500">Last Updated</p>
                      <p className="text-sm text-gray-700 mt-0.5">
                        {featuredRotation.updated_at
                          ? new Date(featuredRotation.updated_at).toLocaleString('en-US', {
                              dateStyle: 'medium',
                              timeStyle: 'short'
                            })
                          : 'Not set'}
                      </p>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Database Sync Card */}
          <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
            <div className="border-b border-gray-200 px-6 py-4">
              <div className="flex items-center gap-3">
                <div className="h-10 w-10 rounded-xl bg-[#105E53] text-white flex items-center justify-center">
                  <Database className="w-5 h-5" />
                </div>
                <div>
                  <h2 className="text-lg font-semibold text-gray-900">Database Sync (Local)</h2>
                  <p className="text-sm text-gray-600">Replace local data with Render staging data</p>
                </div>
              </div>
            </div>

            <div className="p-6 space-y-4">
              <div className="flex items-start gap-3">
                <AlertCircle className="w-5 h-5 text-orange-600 mt-0.5 flex-shrink-0" />
                <div>
                  <p className="text-sm font-semibold text-orange-900">Destructive action</p>
                  <p className="text-sm text-orange-800">
                    This will overwrite your local database. Use only in local development.
                  </p>
                </div>
              </div>

              {lastDbSync && (
                <div className="bg-gray-50 rounded-lg p-4 border border-gray-200 text-sm text-gray-700">
                  {lastDbSync}
                </div>
              )}

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={handleDbSync}
                  disabled={syncingDb}
                  className="px-4 py-2.5 bg-[#0B1D2C] text-white rounded-lg text-sm font-medium hover:bg-[#081620] transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                >
                  {syncingDb ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      Syncing...
                    </>
                  ) : (
                    <>
                      <RefreshCw className="w-4 h-4" />
                      Sync Render to Local
                    </>
                  )}
                </button>
              </div>

              {(syncStatus === 'running' || syncProgress > 0) && (
                <div className="space-y-2">
                  <div className="flex items-center justify-between text-xs text-gray-600">
                    <span>
                      {syncStatus === 'running' ? 'Sync in progress' : 'Sync complete'}
                    </span>
                    <span>{syncProgress}%</span>
                  </div>
                  <div className="h-2 w-full rounded-full bg-gray-100 overflow-hidden">
                    <div
                      className={`h-full transition-all duration-300 ${
                        syncStatus === 'error' ? 'bg-red-500' : 'bg-[#105E53]'
                      }`}
                      style={{ width: `${syncProgress}%` }}
                    />
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      <ToastContainer toasts={toasts} onClose={hideToast} />
    </div>
  );
}
