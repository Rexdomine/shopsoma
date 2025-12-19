import { useState, useEffect } from 'react';
import { Save, DollarSign, Loader2, CheckCircle2, AlertCircle, Truck } from 'lucide-react';
import AdminSidebar from '../../components/admin/AdminSidebar';
import {
  getExchangeRate,
  updateExchangeRate,
  getShippingProviderSettings,
  updateShippingProviderSettings,
  type ExchangeRate,
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
  const [useShipBubble, setUseShipBubble] = useState(false);
  const [savingShipping, setSavingShipping] = useState(false);

  useEffect(() => {
    fetchSettings();
  }, []);

  const fetchSettings = async () => {
    try {
      setLoading(true);
      const [rate, shipping] = await Promise.all([
        getExchangeRate(),
        getShippingProviderSettings()
      ]);
      setExchangeRate(rate);
      setRateInput(rate.rate.toString());
      setUseShipBubble(shipping.use_shipbubble);
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

  const handleToggleShipBubble = async (enabled: boolean) => {
    try {
      setSavingShipping(true);
      const updated = await updateShippingProviderSettings(enabled);
      setUseShipBubble(updated.use_shipbubble);
      success(
        `Shipping provider ${enabled ? 'switched to ShipBubble' : 'switched to local rates'}`,
        'Success'
      );
    } catch (err: any) {
      console.error('Failed to update shipping provider:', err);
      error(
        err.response?.data?.detail || 'Failed to update shipping provider',
        'Error'
      );
      // Revert toggle on error
      setUseShipBubble(!enabled);
    } finally {
      setSavingShipping(false);
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

          {/* Shipping Provider Settings Card */}
          <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
            <div className="border-b border-gray-200 px-6 py-4">
              <div className="flex items-center gap-3">
                <div className="h-10 w-10 rounded-xl bg-[#105E53] text-white flex items-center justify-center">
                  <Truck className="w-5 h-5" />
                </div>
                <div>
                  <h2 className="text-lg font-semibold text-gray-900">Shipping Provider</h2>
                  <p className="text-sm text-gray-600">Configure shipping rate calculation method</p>
                </div>
              </div>
            </div>

            <div className="p-6 space-y-6">
              {/* Toggle Switch */}
              <div className="flex items-center justify-between">
                <div className="flex-1">
                  <label htmlFor="shipbubble-toggle" className="block text-sm font-medium text-gray-900 mb-1">
                    Use ShipBubble API
                  </label>
                  <p className="text-sm text-gray-600">
                    Get real-time shipping rates from ShipBubble couriers
                  </p>
                </div>

                <button
                  id="shipbubble-toggle"
                  type="button"
                  role="switch"
                  aria-checked={useShipBubble}
                  disabled={savingShipping}
                  onClick={() => handleToggleShipBubble(!useShipBubble)}
                  className={`
                    relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent
                    transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-[#105E53] focus:ring-offset-2
                    disabled:opacity-50 disabled:cursor-not-allowed
                    ${useShipBubble ? 'bg-[#105E53]' : 'bg-gray-200'}
                  `}
                >
                  <span className="sr-only">Use ShipBubble</span>
                  <span
                    aria-hidden="true"
                    className={`
                      pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0
                      transition duration-200 ease-in-out
                      ${useShipBubble ? 'translate-x-5' : 'translate-x-0'}
                    `}
                  >
                    {savingShipping && (
                      <Loader2 className="h-5 w-5 animate-spin text-[#105E53]" />
                    )}
                  </span>
                </button>
              </div>

              {/* Status Display */}
              <div className={`rounded-lg p-4 border ${
                useShipBubble
                  ? 'bg-green-50 border-green-200'
                  : 'bg-gray-50 border-gray-200'
              }`}>
                <div className="flex items-start gap-3">
                  {useShipBubble ? (
                    <CheckCircle2 className="w-5 h-5 text-green-600 mt-0.5 flex-shrink-0" />
                  ) : (
                    <AlertCircle className="w-5 h-5 text-gray-600 mt-0.5 flex-shrink-0" />
                  )}
                  <div className="flex-1">
                    <p className={`text-sm font-semibold mb-1 ${
                      useShipBubble ? 'text-green-900' : 'text-gray-900'
                    }`}>
                      Current Provider: {useShipBubble ? 'ShipBubble API' : 'Local Database Rates'}
                    </p>
                    <p className={`text-sm ${
                      useShipBubble ? 'text-green-800' : 'text-gray-700'
                    }`}>
                      {useShipBubble
                        ? 'Using real-time courier rates from ShipBubble. Rates are fetched dynamically during checkout.'
                        : 'Using static rates from the database. Rates are based on predefined zones and weight ranges.'
                      }
                    </p>
                  </div>
                </div>
              </div>

              {/* Info Box */}
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                <div className="flex items-start gap-3">
                  <AlertCircle className="w-5 h-5 text-blue-600 mt-0.5 flex-shrink-0" />
                  <div>
                    <p className="text-sm font-semibold text-blue-900 mb-1">About Shipping Providers</p>
                    <ul className="text-sm text-blue-800 space-y-1">
                      <li><strong>ShipBubble API:</strong> Get real-time rates from multiple couriers (DHL, GIG Logistics, etc.). Requires active API key.</li>
                      <li><strong>Local Rates:</strong> Use predefined shipping rates from your database. Good for testing or custom pricing.</li>
                      <li>• Changes take effect immediately at checkout</li>
                      <li>• ShipBubble automatically falls back to local rates if API fails</li>
                    </ul>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <ToastContainer toasts={toasts} onClose={hideToast} />
    </div>
  );
}
