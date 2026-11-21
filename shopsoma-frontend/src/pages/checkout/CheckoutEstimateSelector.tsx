import axios from 'axios';
import { useEffect, useState } from 'react';
import { Package, Truck } from 'lucide-react';
import type { CheckoutEstimate } from '../../services/checkoutService';

interface Props {
  estimate: CheckoutEstimate;
  selectOption: (estimateId: string, optionId: string) => Promise<CheckoutEstimate>;
  refreshEstimate: () => Promise<CheckoutEstimate>;
  onSelectionConfirmed: (estimate: CheckoutEstimate) => void;
  onStockConflict?: () => void;
  onReturnToBag?: () => void;
  isSubmitting?: boolean;
  disabled?: boolean;
}

const money = (amount: string, currency: string) =>
  `${currency} ${new Intl.NumberFormat('en-NG', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(Number(amount))}`;

const STOCK_CONFLICT_CODES = new Set([
  'insufficient_stock',
  'inventory_subject_unavailable',
  'stock_unavailable',
  'out_of_stock',
]);

function extractConflictCode(caught: unknown): string | null {
  if (!axios.isAxiosError(caught)) return null;
  const detail = (
    caught.response?.data as
      | { detail?: string | { message?: unknown; code?: unknown } }
      | undefined
  )?.detail;
  if (detail && typeof detail === 'object' && typeof detail.code === 'string') {
    const normalized = detail.code.trim().toLowerCase();
    return normalized || null;
  }
  return null;
}

function extractConflictDetail(caught: unknown): string {
  if (!axios.isAxiosError(caught)) return '';
  const detail = (
    caught.response?.data as
      | { detail?: string | { message?: unknown; code?: unknown } }
      | undefined
  )?.detail;
  if (typeof detail === 'string') return detail;
  if (detail && typeof detail === 'object') {
    if (typeof detail.message === 'string') return detail.message;
    if (typeof detail.code === 'string') return detail.code;
  }
  return '';
}

function isStockConflictError(caught: unknown): boolean {
  if (!axios.isAxiosError(caught) || caught.response?.status !== 409) {
    return false;
  }
  const code = extractConflictCode(caught);
  if (code) {
    return STOCK_CONFLICT_CODES.has(code);
  }
  return /insufficient stock|out of stock|inventory subject unavailable|stock_unavailable/i.test(
    extractConflictDetail(caught),
  );
}

export default function CheckoutEstimateSelector({
  estimate: initialEstimate,
  selectOption,
  refreshEstimate,
  onSelectionConfirmed,
  onStockConflict,
  onReturnToBag,
  isSubmitting,
  disabled,
}: Props) {
  const [estimate, setEstimate] = useState(initialEstimate);
  const [selectingId, setSelectingId] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [stockConflict, setStockConflict] = useState(false);

  useEffect(() => {
    setEstimate(initialEstimate);
    setSelectingId(null);
    setError('');
    setStockConflict(false);
  }, [initialEstimate]);

  const choose = async (optionId: string) => {
    setSelectingId(optionId);
    setError('');
    setStockConflict(false);
    try {
      const selected = await selectOption(estimate.id, optionId);
      setEstimate(selected);
    } catch (caught) {
      if (isStockConflictError(caught)) {
        setEstimate((prev) => ({ ...prev, selected_option: null }));
        setStockConflict(true);
        setError(
          'One or more items in your bag are out of stock or no longer available. Return to your bag to remove or update unavailable items.',
        );
        onStockConflict?.();
      } else if (axios.isAxiosError(caught) && caught.response?.status === 409) {
        try {
          const replacement = await refreshEstimate();
          setEstimate(replacement);
          setError('Delivery options changed. Review and explicitly select an available option.');
        } catch (refreshError) {
          if (
            axios.isAxiosError(refreshError)
            && (refreshError.response?.status === 404 || refreshError.response?.status === 410)
          ) {
            setError('Checkout access expired. Start a new checkout to continue.');
          } else {
            setError('Delivery options are still unavailable. Please retry.');
          }
        }
      } else if (axios.isAxiosError(caught) && caught.response?.status === 503) {
        setError('Delivery selection is temporarily unavailable. Please retry.');
      } else {
        setError('Delivery selection failed. Please retry.');
      }
    } finally {
      setSelectingId(null);
    }
  };

  return (
    <section className="space-y-3" aria-label="Server delivery options">
      <p className="text-xs text-gray-600">
        Select one delivery option. Expires {new Date(estimate.expires_at).toLocaleString()}.
      </p>
      {estimate.options.map((option) => {
        const selected = estimate.selected_option?.id === option.id;
        const isSelecting = selectingId === option.id;
        const delivery = option.min_delivery_days === null || option.max_delivery_days === null
          ? 'Delivery timing confirmed after selection'
          : `${option.min_delivery_days}–${option.max_delivery_days} business days`;
        return (
          <div
            key={option.id}
            className={`border rounded-sm p-3.5 sm:px-4 sm:py-3.5 overflow-hidden transition-colors ${
              selected ? 'border-primary bg-gray-50' : 'border-gray-200 bg-white'
            }`}
          >
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
              <div className="flex items-start sm:items-center gap-3 min-w-0 flex-1">
                {option.provider_metadata?.courier_image ? (
                  <img
                    src={option.provider_metadata.courier_image}
                    alt=""
                    className="h-9 w-9 object-contain rounded shrink-0 bg-white border border-gray-100 p-1"
                  />
                ) : option.provider_metadata?.provider === 'dhl' || option.service_label?.toLowerCase().includes('dhl') ? (
                  <div className="h-9 w-9 rounded shrink-0 bg-[#FFCC00] flex items-center justify-center font-black text-xs text-[#D40511] tracking-tight border border-[#E5B800] shadow-xs">
                    DHL
                  </div>
                ) : option.provider_metadata?.provider === 'manual' || Boolean(option.provider_metadata?.rate_id) ? (
                  <div className="h-9 w-9 rounded shrink-0 bg-slate-100 flex items-center justify-center text-slate-700 border border-slate-200">
                    <Package className="h-5 w-5" />
                  </div>
                ) : option.provider_metadata?.provider === 'shipbubble' ? (
                  <div className="h-9 w-9 rounded shrink-0 bg-emerald-50 flex items-center justify-center text-[#105E53] border border-emerald-100">
                    <Truck className="h-5 w-5" />
                  </div>
                ) : null}
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-semibold text-gray-900 break-words leading-snug">
                    {option.service_label}
                  </p>
                  <p className="text-xs text-gray-500 mt-0.5">{delivery}</p>
                </div>
              </div>
              <div className="flex items-center justify-between sm:flex-col sm:items-end sm:justify-center gap-2 pt-2.5 sm:pt-0 border-t sm:border-t-0 border-gray-100 shrink-0">
                <p className="text-sm font-semibold text-gray-900 whitespace-nowrap">
                  {money(option.amount, option.currency)}
                </p>
                <button
                  type="button"
                  onClick={() => choose(option.id)}
                  disabled={Boolean(selectingId) || selected || Boolean(isSubmitting) || Boolean(disabled) || stockConflict}
                  aria-label={selected ? `Selected ${option.service_label}` : isSelecting ? 'Selecting…' : `Select ${option.service_label}`}
                  className={`px-3.5 py-1.5 rounded-sm border text-xs font-semibold transition-colors whitespace-nowrap disabled:opacity-50 ${
                    selected
                      ? 'border-primary bg-primary text-white'
                      : 'border-primary text-primary hover:bg-primary/5'
                  }`}
                >
                  {selected ? 'Selected' : isSelecting ? 'Selecting…' : 'Select'}
                </button>
              </div>
            </div>
          </div>
        );
      })}
      {error && (
        <div role="alert" className={`space-y-2 rounded-sm border p-3 ${stockConflict ? 'border-red-200 bg-red-50 text-red-800' : 'border-amber-200 bg-amber-50 text-amber-800'}`}>
          <p className="text-sm">{error}</p>
          {stockConflict && onReturnToBag && (
            <button
              type="button"
              onClick={onReturnToBag}
              className="text-xs font-semibold underline text-red-900 hover:text-red-700"
            >
              Return to Bag
            </button>
          )}
        </div>
      )}
      <button
        type="button"
        disabled={!estimate.selected_option || Boolean(selectingId) || Boolean(isSubmitting) || Boolean(disabled) || stockConflict}
        onClick={() => onSelectionConfirmed(estimate)}
        className="w-full py-3 rounded-sm bg-primary text-white text-sm font-semibold disabled:opacity-50 flex items-center justify-center gap-2"
      >
        {isSubmitting && (
          <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
        )}
        {isSubmitting ? 'Preparing payment…' : 'Continue to payment'}
      </button>
    </section>
  );
}
