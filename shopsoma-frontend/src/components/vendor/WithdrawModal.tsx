import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { X, ChevronDown, Check } from 'lucide-react';
import { useVendor } from '../../context/VendorContext';
import { vendorService } from '../../services/vendorService';
import { formatPriceWithConversion } from '../../utils/pricing';
import { useCurrencyStore } from '../../store/currencyStore';
import { vendorPaymentMethodsService, type PaymentMethod } from '../../services/vendorPaymentMethodsService';

type WithdrawModalProps = {
  open: boolean;
  onClose: () => void;
  onSuccess?: (message: string) => void;
  onError?: (message: string) => void;
};

export default function WithdrawModal({ open, onClose, onSuccess, onError }: WithdrawModalProps) {
  const { vendorProfile } = useVendor();
  const { currentCurrency, exchangeRates, fetchExchangeRate } = useCurrencyStore();
  const [amount, setAmount] = useState(0);
  const [account, setAccount] = useState('');
  const [paymentMethods, setPaymentMethods] = useState<PaymentMethod[]>([]);
  const [selectedMethodId, setSelectedMethodId] = useState<string | null>(null);
  const [openAccountList, setOpenAccountList] = useState(false);
  const [currentEarnings, setCurrentEarnings] = useState<number | null>(null);
  const [availablePayout, setAvailablePayout] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const listRef = useRef<HTMLDivElement | null>(null);
  const minAmount = 50000;
  const step = 50000;

  const accounts = useMemo(() => {
    if (paymentMethods.length) {
      return paymentMethods.map((method) => ({
        id: method.id,
        label: `${method.bank_name} (${method.masked_account})`,
        isDefault: method.is_default,
      }));
    }
    if (!vendorProfile?.bank_name || !vendorProfile?.bank_account_number) {
      return [];
    }
    const last4 = vendorProfile.bank_account_number.slice(-4);
    const masked = `xxxx${last4}`;
    return [{ id: 'legacy', label: `${vendorProfile.bank_name} (${masked})`, isDefault: true }];
  }, [paymentMethods, vendorProfile?.bank_account_number, vendorProfile?.bank_name]);

  useEffect(() => {
    if (!open) {
      setAmount(0);
      setAccount(accounts[0]?.label || '');
      setSelectedMethodId(accounts[0]?.id || null);
      setOpenAccountList(false);
      setError(null);
      setCurrentEarnings(null);
      setAvailablePayout(null);
    }
  }, [open, accounts]);

  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (listRef.current && !listRef.current.contains(e.target as Node)) {
        setOpenAccountList(false);
      }
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  useEffect(() => {
    fetchExchangeRate();
  }, [fetchExchangeRate]);

  useEffect(() => {
    const fetchMethods = async () => {
      if (!open) return;
      try {
        const methods = await vendorPaymentMethodsService.list();
        const sorted = [...methods].sort((a, b) => {
          if (a.is_default === b.is_default) {
            return a.created_at > b.created_at ? -1 : 1;
          }
          return a.is_default ? -1 : 1;
        });
        setPaymentMethods(sorted);
        if (sorted.length) {
          setAccount(`${sorted[0].bank_name} (${sorted[0].masked_account})`);
          setSelectedMethodId(sorted[0].id);
        }
      } catch (err) {
        setPaymentMethods([]);
      }
    };
    fetchMethods();
  }, [open]);

  const loadSummary = useCallback(async () => {
    if (!open) return;
    try {
      setLoading(true);
      setError(null);
      const summary = await vendorService.getPayoutSummary();
      const current = Number(summary.current_earnings ?? 0);
      const available = Number(summary.available_payout ?? 0);
      setCurrentEarnings(current);
      setAvailablePayout(available);
      const initial = Math.min(500000, available);
      setAmount(initial > 0 ? initial : 0);
    } catch (err: any) {
      setError(err?.message || 'Failed to load payout balance.');
    } finally {
      setLoading(false);
    }
  }, [open]);

  useEffect(() => {
    loadSummary();
  }, [loadSummary]);

  if (!open) return null;

  const handleIncrement = () =>
    setAmount((prev) => Math.min(availablePayout ?? 0, prev + step));
  const handleDecrement = () => setAmount((prev) => Math.max(minAmount, prev - step));

  const canWithdraw = (availablePayout ?? 0) >= minAmount && amount >= minAmount && !!account;
  const formattedAmount = formatPriceWithConversion(amount, 'NGN', currentCurrency, exchangeRates);
  const formatOptionalAmount = (value: number | null) => {
    if (value === null) {
      return '—';
    }
    return formatPriceWithConversion(value, 'NGN', currentCurrency, exchangeRates);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-[1px] px-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md p-6 relative">
        <button
          type="button"
          onClick={onClose}
          className="absolute right-4 top-4 text-gray-400 hover:text-gray-600"
          aria-label="Close"
        >
          <X className="w-5 h-5" />
        </button>
        <h3 className="text-sm font-semibold text-gray-800 mb-6">Withdraw Earnings</h3>

        <div className="flex items-center justify-center gap-4 mb-4">
          <button
            type="button"
            onClick={handleDecrement}
            className="h-8 w-8 rounded-full border border-gray-300 flex items-center justify-center text-lg text-gray-700 hover:bg-gray-50"
            aria-label="Decrease amount"
            disabled={!canWithdraw}
          >
            –
          </button>
          <div className="text-3xl font-semibold text-gray-900 tracking-tight">
            {formattedAmount}
          </div>
          <button
            type="button"
            onClick={handleIncrement}
            className="h-8 w-8 rounded-full border border-gray-300 flex items-center justify-center text-lg text-gray-700 hover:bg-gray-50"
            aria-label="Increase amount"
            disabled={!canWithdraw}
          >
            +
          </button>
        </div>
        <p className="text-xs text-gray-500 text-center mb-4">Est. Transfer Time: 3 days</p>
        <div className="grid grid-cols-2 gap-3 mb-4">
          <div className="rounded-xl border border-gray-200 bg-gray-50 px-4 py-3 text-left">
            <p className="text-xs text-gray-500">Current Earnings</p>
            <p className="text-sm font-semibold text-gray-900">
              {loading ? (
                <span className="inline-block h-3 w-16 bg-gray-200 rounded-full animate-pulse" />
              ) : (
                formatOptionalAmount(currentEarnings)
              )}
            </p>
          </div>
          <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-left">
            <p className="text-xs text-emerald-700">Available Payout</p>
            <p className="text-sm font-semibold text-emerald-900">
              {loading ? (
                <span className="inline-block h-3 w-16 bg-emerald-200 rounded-full animate-pulse" />
              ) : (
                formatOptionalAmount(availablePayout)
              )}
            </p>
          </div>
        </div>
        {loading && (
          <div className="mb-4 space-y-2">
            <div className="h-3 w-40 bg-gray-200 rounded-full animate-pulse mx-auto" />
            <div className="h-3 w-24 bg-gray-200 rounded-full animate-pulse mx-auto" />
          </div>
        )}
        {!loading && (
          <p className="text-xs text-gray-500 text-center mb-4">
            Available to withdraw: {formatOptionalAmount(availablePayout)}
          </p>
        )}
        {error && (
          <div className="text-center mb-4 space-y-2">
            <p className="text-xs text-red-600">{error}</p>
            <button
              type="button"
              onClick={loadSummary}
              className="text-xs font-semibold text-[#105E53] hover:underline"
            >
              Retry
            </button>
          </div>
        )}

        <div className="space-y-2">
          <p className="text-sm text-gray-600">Choose Account</p>
          <div className="relative" ref={listRef}>
            <button
              type="button"
              onClick={() => setOpenAccountList((prev) => !prev)}
              className="w-full border border-gray-300 rounded-lg px-4 py-3 text-sm text-gray-800 bg-white flex items-center justify-between focus:outline-none focus:ring-2 focus:ring-[#105E53] focus:border-transparent"
              disabled={accounts.length === 0}
            >
              <span className="truncate">{account || 'Add payout info in settings'}</span>
              <ChevronDown className={`w-4 h-4 text-gray-500 transition ${openAccountList ? 'rotate-180' : ''}`} />
            </button>
            {openAccountList && (
              <div className="absolute z-10 mt-2 w-full bg-white border border-gray-200 rounded-lg shadow-lg overflow-hidden">
                {accounts.map((acc) => (
                  <button
                    key={acc.id}
                    type="button"
                    onClick={() => {
                      setAccount(acc.label);
                      setSelectedMethodId(acc.id === 'legacy' ? null : acc.id);
                      setOpenAccountList(false);
                    }}
                    className={`w-full px-4 py-3 text-left text-sm flex items-center justify-between hover:bg-gray-50 ${
                      acc.label === account ? 'text-gray-900 font-semibold' : 'text-gray-700'
                    }`}
                  >
                    <span className="truncate">{acc.label}</span>
                    {acc.label === account && <Check className="w-4 h-4 text-[#105E53]" />}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        <button
          type="button"
          className="mt-6 w-full bg-[#105E53] text-white font-semibold rounded-lg py-3 hover:bg-[#0c4c45] transition disabled:opacity-50 disabled:cursor-not-allowed"
          disabled={!canWithdraw || submitting}
          onClick={async () => {
            try {
              setSubmitting(true);
              setError(null);
              await vendorService.requestPayout({
                amount,
                payment_method_id: selectedMethodId || undefined,
              });
              onSuccess?.('Withdrawal request submitted.');
              onClose();
            } catch (err: any) {
              const message = err?.message || 'Failed to request withdrawal.';
              setError(message);
              onError?.(message);
            } finally {
              setSubmitting(false);
            }
          }}
        >
          {submitting ? 'Submitting...' : 'Begin Withdrawal'}
        </button>
      </div>
    </div>
  );
}
