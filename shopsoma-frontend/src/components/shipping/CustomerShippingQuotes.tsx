import { isAxiosError } from 'axios';
import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import {
  shippingQuoteService,
  type CustomerShippingQuote,
  type CustomerShippingQuoteOption,
} from '../../services/shippingQuoteService';

interface CustomerShippingQuotesProps {
  orderId: string;
}

interface PendingSelection {
  orderId: string;
  quoteId: string;
  optionId: string;
  key: string;
  generation: number;
}

function sameSelection(left: PendingSelection | null, right: PendingSelection): boolean {
  return left !== null
    && left.orderId === right.orderId
    && left.quoteId === right.quoteId
    && left.optionId === right.optionId
    && left.key === right.key
    && left.generation === right.generation;
}

function isDefinitiveSelectionRejection(error: unknown): boolean {
  const status = isAxiosError(error) ? error.response?.status : undefined;
  return status !== undefined && status >= 400 && status < 500;
}

const SAFE_ERROR = 'Delivery options are unavailable right now. Please try again.';
const MAX_TIMER_DELAY_MS = 2_147_483_647;

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

function effectiveQuoteStatus(
  quote: CustomerShippingQuote,
  nowMs: number,
): CustomerShippingQuote['status'] {
  if (quote.status === 'available' && Date.parse(quote.expires_at) <= nowMs) {
    return 'expired';
  }
  return quote.status;
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
  const [nowMs, setNowMs] = useState(() => Date.now());
  const [pendingSelection, setPendingSelection] = useState<PendingSelection | null>(null);
  const pendingSelectionRef = useRef<PendingSelection | null>(null);
  const inFlightSelectionRef = useRef<PendingSelection | null>(null);
  const selectionGenerationRef = useRef(0);
  const latestOrderIdRef = useRef(orderId);
  const pendingQuoteKey = useRef<string | null>(null);

  useLayoutEffect(() => {
    latestOrderIdRef.current = orderId;
    selectionGenerationRef.current += 1;
    pendingQuoteKey.current = null;
    pendingSelectionRef.current = null;
    inFlightSelectionRef.current = null;
    setPendingSelection(null);
    setSelectingOptionId(null);
  }, [orderId]);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setLoadFailed(false);
    setMessage('');
    shippingQuoteService
      .listQuotes(orderId)
      .then((data) => {
        if (active) {
          setQuotes(data);
          setNowMs(Date.now());
        }
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

  useEffect(() => {
    const nextExpiry = quotes
      .filter((quote) => quote.status === 'available')
      .map((quote) => Date.parse(quote.expires_at))
      .filter((expiry) => Number.isFinite(expiry) && expiry > nowMs)
      .sort((left, right) => left - right)[0];
    if (nextExpiry === undefined) return undefined;
    const timer = window.setTimeout(
      () => setNowMs(Date.now()),
      Math.min(MAX_TIMER_DELAY_MS, Math.max(0, nextExpiry - Date.now())),
    );
    return () => window.clearTimeout(timer);
  }, [quotes, nowMs]);

  const requestQuote = async () => {
    if (requesting || pendingSelectionRef.current !== null) return;
    setRequesting(true);
    setLoadFailed(false);
    setMessage('');
    const idempotencyKey = pendingQuoteKey.current ?? actionKey('quote');
    pendingQuoteKey.current = idempotencyKey;
    try {
      const quote = await shippingQuoteService.createQuote(orderId, idempotencyKey);
      pendingQuoteKey.current = null;
      setQuotes((current) => [quote, ...current.filter((item) => item.id !== quote.id)]);
      setNowMs(Date.now());
      setMessage('Delivery options are ready.');
    } catch {
      setMessage(SAFE_ERROR);
    } finally {
      setRequesting(false);
    }
  };

  const selectOption = async (quote: CustomerShippingQuote, option: CustomerShippingQuoteOption) => {
    if (inFlightSelectionRef.current !== null) return;

    const existingSelection = pendingSelectionRef.current;
    const matchesExisting = existingSelection !== null
      && existingSelection.orderId === orderId
      && existingSelection.quoteId === quote.id
      && existingSelection.optionId === option.id;
    if (existingSelection !== null && !matchesExisting) {
      setMessage(SAFE_ERROR);
      return;
    }
    if (!matchesExisting && effectiveQuoteStatus(quote, Date.now()) !== 'available') return;

    const selectionRequest: PendingSelection = existingSelection ?? {
      orderId,
      quoteId: quote.id,
      optionId: option.id,
      key: actionKey('selection'),
      generation: selectionGenerationRef.current + 1,
    };
    if (existingSelection === null) {
      selectionGenerationRef.current = selectionRequest.generation;
      pendingSelectionRef.current = selectionRequest;
      setPendingSelection(selectionRequest);
    }
    inFlightSelectionRef.current = selectionRequest;
    setSelectingOptionId(option.id);
    setMessage('');

    const remainsAuthoritative = () => latestOrderIdRef.current === selectionRequest.orderId
      && sameSelection(pendingSelectionRef.current, selectionRequest)
      && sameSelection(inFlightSelectionRef.current, selectionRequest);

    try {
      const updated = await shippingQuoteService.selectOption(
        selectionRequest.orderId,
        selectionRequest.quoteId,
        selectionRequest.optionId,
        selectionRequest.key,
      );
      if (!remainsAuthoritative()) return;
      pendingSelectionRef.current = null;
      inFlightSelectionRef.current = null;
      setPendingSelection(null);
      setSelectingOptionId(null);
      setQuotes((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      setMessage('Delivery option selected.');
    } catch (error) {
      if (!remainsAuthoritative()) return;
      if (isDefinitiveSelectionRejection(error)) {
        pendingSelectionRef.current = null;
        setPendingSelection(null);
      }
      inFlightSelectionRef.current = null;
      setSelectingOptionId(null);
      setMessage(SAFE_ERROR);
    }
  };

  if (loading) {
    return <p className="text-sm text-gray-500" role="status">Loading delivery options…</p>;
  }

  const displayQuotes = quotes.map((quote) => ({
    ...quote,
    status: effectiveQuoteStatus(quote, nowMs),
  }));
  const hasSelectableQuote = displayQuotes.some((quote) => quote.status === 'available');

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
        {displayQuotes.map((quote) => (
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
                const matchingPending = pendingSelection !== null
                  && pendingSelection.orderId === orderId
                  && pendingSelection.quoteId === quote.id
                  && pendingSelection.optionId === option.id;
                const selecting = selectingOptionId === option.id && matchingPending;
                const recovering = unavailable && matchingPending;
                const disabled = quote.status === 'selected'
                  || selectingOptionId !== null
                  || (unavailable && !recovering)
                  || (pendingSelection !== null && !matchingPending);
                const buttonLabel = selected
                  ? `Selected ${option.service_label}`
                  : selecting
                    ? 'Selecting…'
                    : recovering
                      ? `Retry selection for ${option.service_label}`
                      : unavailable
                        ? `${quote.status === 'expired' ? 'Expired' : 'Unavailable'} ${option.service_label}`
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
                      {selected
                        ? 'Selected'
                        : selecting
                          ? 'Selecting…'
                          : recovering
                            ? 'Retry selection'
                            : unavailable
                              ? quote.status === 'expired' ? 'Expired' : 'Unavailable'
                              : 'Choose'}
                    </button>
                  </div>
                );
              })}
            </div>
          </article>
        ))}
      </div>

      {!hasSelectableQuote && !displayQuotes.some((quote) => quote.status === 'selected') && (
        <button
          type="button"
          disabled={requesting || pendingSelection !== null}
          aria-label={loadFailed
            ? 'Retry loading delivery options'
            : pendingSelection !== null
              ? 'Resolve pending delivery selection first'
              : undefined}
          onClick={loadFailed ? () => setReloadToken((value) => value + 1) : requestQuote}
          className="min-h-11 w-full rounded-sm border border-primary px-4 py-2 text-sm font-semibold text-primary transition hover:bg-primary/5 disabled:cursor-not-allowed disabled:opacity-60 sm:w-auto"
        >
          {requesting
            ? 'Getting delivery options…'
            : pendingSelection !== null
              ? 'Resolve pending selection first'
              : loadFailed || message === SAFE_ERROR ? 'Try again' : 'Get delivery options'}
        </button>
      )}

      <p aria-live="polite" role="status" className={`text-sm ${message === SAFE_ERROR ? 'text-red-700' : 'text-emerald-700'}`}>
        {message}
      </p>
    </section>
  );
}
