import { useEffect, useState } from 'react';
import {
  shippingQuoteService,
  type CustomerShippingQuote,
  type CustomerShippingQuoteOption,
} from '../../services/shippingQuoteService';

interface CustomerShippingQuotesProps {
  orderId: string;
}

const SAFE_ERROR = 'Delivery options are unavailable right now. Please try again.';

function actionKey(prefix: 'quote' | 'selection'): string {
  const random = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  return `${prefix}-${random}`;
}

function formatAmount(amount: string, currency: string): string {
  const numericAmount = Number(amount);
  if (!Number.isFinite(numericAmount)) return `${currency} ${amount}`;
  return `${currency} ${numericAmount.toLocaleString('en-NG', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

function optionTiming(option: CustomerShippingQuoteOption): string | null {
  const details: string[] = [];
  if (option.transit_days != null) {
    details.push(`${option.transit_days} business day${option.transit_days === 1 ? '' : 's'}`);
  }
  if (option.delivery_date) {
    details.push(`Estimated delivery ${new Date(`${option.delivery_date}T00:00:00`).toLocaleDateString('en-GB', {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
    })}`);
  }
  return details.length > 0 ? details.join(' · ') : null;
}

export default function CustomerShippingQuotes({ orderId }: CustomerShippingQuotesProps) {
  const [quotes, setQuotes] = useState<CustomerShippingQuote[]>([]);
  const [loading, setLoading] = useState(true);
  const [requesting, setRequesting] = useState(false);
  const [selectingOptionId, setSelectingOptionId] = useState<string | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [reloadToken, setReloadToken] = useState(0);
  const [message, setMessage] = useState('');

  useEffect(() => {
    let active = true;
    setLoading(true);
    setLoadFailed(false);
    setMessage('');
    shippingQuoteService
      .listQuotes(orderId)
      .then((data) => {
        if (active) setQuotes(data);
      })
      .catch(() => {
        if (active) {
          setQuotes([]);
          setLoadFailed(true);
          setMessage(SAFE_ERROR);
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [orderId, reloadToken]);

  const requestQuote = async () => {
    if (requesting) return;
    setRequesting(true);
    setLoadFailed(false);
    setMessage('');
    try {
      const quote = await shippingQuoteService.createQuote(orderId, actionKey('quote'));
      setQuotes((current) => [quote, ...current.filter((item) => item.id !== quote.id)]);
      setMessage('Delivery options are ready.');
    } catch {
      setMessage(SAFE_ERROR);
    } finally {
      setRequesting(false);
    }
  };

  const selectOption = async (quote: CustomerShippingQuote, option: CustomerShippingQuoteOption) => {
    if (selectingOptionId || quote.status !== 'available') return;
    setSelectingOptionId(option.id);
    setMessage('');
    try {
      const updated = await shippingQuoteService.selectOption(
        orderId,
        quote.id,
        option.id,
        actionKey('selection'),
      );
      setQuotes((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      setMessage('Delivery option selected.');
    } catch {
      setMessage(SAFE_ERROR);
    } finally {
      setSelectingOptionId(null);
    }
  };

  if (loading) {
    return <p className="text-sm text-gray-500" role="status">Loading delivery options…</p>;
  }

  const hasSelectableQuote = quotes.some((quote) => quote.status === 'available');

  return (
    <section aria-labelledby={`shipping-quotes-${orderId}`} className="border-t border-gray-200 pt-5 space-y-4">
      <div>
        <h3 id={`shipping-quotes-${orderId}`} className="text-sm font-semibold text-gray-700 uppercase tracking-[0.2em]">
          Secure delivery options
        </h3>
        <p className="mt-1 text-xs text-gray-500">
          Rates are tied to this order and shown in the order currency.
        </p>
      </div>

      {quotes.length === 0 && !loadFailed && (
        <p className="text-sm text-gray-600">No delivery quote has been requested for this order.</p>
      )}

      <div className="space-y-4">
        {quotes.map((quote) => (
          <article key={quote.id} className="rounded-sm border border-gray-200 p-4 space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-xs font-semibold uppercase tracking-wide text-gray-600">{quote.status}</span>
              <span className="text-xs text-gray-500">
                {quote.status === 'expired'
                  ? 'Quote expired'
                  : `Valid until ${new Date(quote.expires_at).toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' })}`}
              </span>
            </div>
            <div className="space-y-2">
              {quote.options.map((option) => {
                const selected = quote.selected_option_id === option.id;
                const unavailable = quote.status === 'expired' || quote.status === 'superseded';
                const selecting = selectingOptionId === option.id;
                const disabled = unavailable || quote.status === 'selected' || selectingOptionId !== null;
                const buttonLabel = selected
                  ? `Selected ${option.service_label}`
                  : unavailable
                    ? `${quote.status === 'expired' ? 'Expired' : 'Unavailable'} ${option.service_label}`
                    : selecting
                      ? 'Selecting…'
                      : `Choose ${option.service_label}`;
                return (
                  <div key={option.id} className="flex flex-col gap-3 rounded-sm bg-gray-50 p-3 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                      <p className="text-sm font-semibold text-gray-900">{option.service_label}</p>
                      <p className="text-sm text-gray-700">{formatAmount(option.total_amount, option.currency)}</p>
                      {optionTiming(option) && <p className="text-xs text-gray-500">{optionTiming(option)}</p>}
                    </div>
                    <button
                      type="button"
                      disabled={disabled}
                      aria-label={buttonLabel}
                      onClick={() => selectOption(quote, option)}
                      className="min-h-11 rounded-sm bg-primary px-4 py-2 text-sm font-semibold text-white transition hover:bg-primary-dark disabled:cursor-not-allowed disabled:bg-gray-300"
                    >
                      {selected ? 'Selected' : unavailable ? (quote.status === 'expired' ? 'Expired' : 'Unavailable') : selecting ? 'Selecting…' : 'Choose'}
                    </button>
                  </div>
                );
              })}
            </div>
          </article>
        ))}
      </div>

      {!hasSelectableQuote && !quotes.some((quote) => quote.status === 'selected') && (
        <button
          type="button"
          disabled={requesting}
          aria-label={loadFailed ? 'Retry loading delivery options' : undefined}
          onClick={loadFailed ? () => setReloadToken((value) => value + 1) : requestQuote}
          className="min-h-11 w-full rounded-sm border border-primary px-4 py-2 text-sm font-semibold text-primary transition hover:bg-primary/5 disabled:cursor-not-allowed disabled:opacity-60 sm:w-auto"
        >
          {requesting ? 'Getting delivery options…' : loadFailed || message === SAFE_ERROR ? 'Try again' : 'Get delivery options'}
        </button>
      )}

      <p aria-live="polite" role="status" className={`text-sm ${message === SAFE_ERROR ? 'text-red-700' : 'text-emerald-700'}`}>
        {message}
      </p>
    </section>
  );
}
