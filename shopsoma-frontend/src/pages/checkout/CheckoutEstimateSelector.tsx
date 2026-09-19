import axios from 'axios';
import { useEffect, useState } from 'react';
import type { CheckoutEstimate } from '../../services/checkoutService';

interface Props {
  estimate: CheckoutEstimate;
  selectOption: (estimateId: string, optionId: string) => Promise<CheckoutEstimate>;
  refreshEstimate: () => Promise<CheckoutEstimate>;
  onSelectionConfirmed: (estimate: CheckoutEstimate) => void;
}

const money = (amount: string, currency: string) =>
  `${currency} ${new Intl.NumberFormat('en-NG', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(Number(amount))}`;

export default function CheckoutEstimateSelector({
  estimate: initialEstimate,
  selectOption,
  refreshEstimate,
  onSelectionConfirmed,
}: Props) {
  const [estimate, setEstimate] = useState(initialEstimate);
  const [selectingId, setSelectingId] = useState<string | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    setEstimate(initialEstimate);
    setSelectingId(null);
    setError('');
  }, [initialEstimate]);

  const choose = async (optionId: string) => {
    setSelectingId(optionId);
    setError('');
    try {
      const selected = await selectOption(estimate.id, optionId);
      setEstimate(selected);
    } catch (caught) {
      if (axios.isAxiosError(caught) && caught.response?.status === 409) {
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
        const delivery = option.min_delivery_days === null || option.max_delivery_days === null
          ? 'Delivery timing confirmed after selection'
          : `${option.min_delivery_days}–${option.max_delivery_days} business days`;
        return (
          <div key={option.id} className={`border px-4 py-3 ${selected ? 'border-primary bg-gray-50' : 'border-gray-200'}`}>
            <div className="flex items-center justify-between gap-4">
              <div>
                <p className="text-sm font-semibold">{option.service_label}</p>
                <p className="text-xs text-gray-500">{delivery}</p>
              </div>
              <div className="text-right">
                <p className="text-sm font-semibold">{money(option.amount, option.currency)}</p>
                <button
                  type="button"
                  onClick={() => choose(option.id)}
                  disabled={Boolean(selectingId) || selected}
                  className="mt-2 px-3 py-1 border border-primary text-primary text-xs disabled:opacity-50"
                >
                  {selected ? `Selected ${option.service_label}` : selectingId === option.id ? 'Selecting…' : `Select ${option.service_label}`}
                </button>
              </div>
            </div>
          </div>
        );
      })}
      {error && <p role="alert" className="text-sm text-amber-700">{error}</p>}
      <button
        type="button"
        disabled={!estimate.selected_option || Boolean(selectingId)}
        onClick={() => onSelectionConfirmed(estimate)}
        className="w-full py-3 rounded-sm bg-primary text-white text-sm font-semibold disabled:opacity-50"
      >
        Continue to payment
      </button>
    </section>
  );
}
