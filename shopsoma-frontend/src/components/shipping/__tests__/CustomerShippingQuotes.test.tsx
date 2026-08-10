import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { CustomerShippingQuote } from '../../../services/shippingQuoteService';
import CustomerShippingQuotes from '../CustomerShippingQuotes';

const { listQuotes, createQuote, selectOption } = vi.hoisted(() => ({
  listQuotes: vi.fn(),
  createQuote: vi.fn(),
  selectOption: vi.fn(),
}));

const SAFE_ERROR = 'Delivery options are unavailable right now. Please try again.';

vi.mock('../../../services/shippingQuoteService', () => ({
  shippingQuoteService: { listQuotes, createQuote, selectOption },
}));

const availableQuote: CustomerShippingQuote = {
  id: 'quote-1',
  order_id: 'order-1',
  currency: 'NGN',
  expires_at: '2099-01-01T12:00:00Z',
  created_at: '2099-01-01T11:00:00Z',
  status: 'available' as const,
  selected_option_id: null,
  options: [
    {
      id: 'option-1',
      service_label: 'DHL Express Domestic',
      total_amount: '4500.00',
      currency: 'NGN',
      transit_days: 2,
      delivery_date: '2099-01-03',
    },
  ],
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

function quoteForOrder(orderId: string, quoteId: string, optionId: string, serviceLabel: string) {
  return {
    ...availableQuote,
    id: quoteId,
    order_id: orderId,
    options: [{
      ...availableQuote.options[0],
      id: optionId,
      service_label: serviceLabel,
    }],
  };
}

describe('CustomerShippingQuotes', () => {
  beforeEach(() => {
    listQuotes.mockReset();
    createQuote.mockReset();
    selectOption.mockReset();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('loads existing authoritative quotes and renders response currency without conversion', async () => {
    listQuotes.mockResolvedValue([availableQuote]);
    render(<CustomerShippingQuotes orderId="order-1" />);

    expect(screen.getByText('Loading delivery options…')).toBeInTheDocument();
    expect(await screen.findByText('DHL Express Domestic')).toBeInTheDocument();
    expect(screen.getByText(/NGN\s*4,500\.00/)).toBeInTheDocument();
    expect(screen.getByText(/2 business days/)).toBeInTheDocument();
  });

  it('requests a quote from the empty state with one stable idempotency key', async () => {
    listQuotes.mockResolvedValue([]);
    createQuote.mockResolvedValue(availableQuote);
    render(<CustomerShippingQuotes orderId="order-1" />);

    fireEvent.click(await screen.findByRole('button', { name: 'Get delivery options' }));
    fireEvent.click(screen.getByRole('button', { name: 'Getting delivery options…' }));

    await waitFor(() => expect(createQuote).toHaveBeenCalledTimes(1));
    expect(createQuote).toHaveBeenCalledWith('order-1', expect.stringMatching(/^quote-/));
    expect(await screen.findByText('DHL Express Domestic')).toBeInTheDocument();
  });

  it('selects an eligible option once and announces success', async () => {
    listQuotes.mockResolvedValue([availableQuote]);
    selectOption.mockResolvedValue({
      ...availableQuote,
      status: 'selected',
      selected_option_id: 'option-1',
    });
    render(<CustomerShippingQuotes orderId="order-1" />);

    const button = await screen.findByRole('button', { name: 'Choose DHL Express Domestic' });
    fireEvent.click(button);
    fireEvent.click(screen.getByRole('button', { name: 'Selecting…' }));

    await waitFor(() => expect(selectOption).toHaveBeenCalledTimes(1));
    expect(selectOption).toHaveBeenCalledWith(
      'order-1',
      'quote-1',
      'option-1',
      expect.stringMatching(/^selection-/),
    );
    expect(await screen.findByText('Delivery option selected.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Selected DHL Express Domestic' })).toBeDisabled();
  });

  it('reuses the same selection key after an ambiguous response failure', async () => {
    listQuotes.mockResolvedValue([availableQuote]);
    selectOption
      .mockRejectedValueOnce(new Error('response lost after commit'))
      .mockResolvedValueOnce({
        ...availableQuote,
        status: 'selected',
        selected_option_id: 'option-1',
      });
    render(<CustomerShippingQuotes orderId="order-1" />);

    fireEvent.click(await screen.findByRole('button', { name: 'Choose DHL Express Domestic' }));
    expect(await screen.findByText('Delivery options are unavailable right now. Please try again.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Choose DHL Express Domestic' }));

    await waitFor(() => expect(selectOption).toHaveBeenCalledTimes(2));
    expect(selectOption.mock.calls[0][3]).toBe(selectOption.mock.calls[1][3]);
    expect(await screen.findByRole('button', { name: 'Selected DHL Express Domestic' })).toBeDisabled();
  });

  it('keeps same-key selection recovery available after the quote expires', async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2099-01-01T11:59:59Z'));
    const expiringQuote = { ...availableQuote, expires_at: '2099-01-01T12:00:00Z' };
    listQuotes.mockResolvedValue([expiringQuote]);
    selectOption
      .mockRejectedValueOnce(new Error('response lost after commit'))
      .mockResolvedValueOnce({
        ...expiringQuote,
        status: 'selected',
        selected_option_id: 'option-1',
      });
    render(<CustomerShippingQuotes orderId="order-1" />);

    await vi.waitFor(() => {
      expect(screen.getByRole('button', { name: 'Choose DHL Express Domestic' })).toBeEnabled();
    });
    fireEvent.click(screen.getByRole('button', { name: 'Choose DHL Express Domestic' }));
    await vi.waitFor(() => expect(selectOption).toHaveBeenCalledTimes(1));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });

    const retry = screen.getByRole('button', { name: 'Retry selection for DHL Express Domestic' });
    expect(retry).toBeEnabled();
    fireEvent.click(retry);
    await vi.waitFor(() => expect(selectOption).toHaveBeenCalledTimes(2));
    expect(selectOption.mock.calls[0][3]).toBe(selectOption.mock.calls[1][3]);
    await vi.waitFor(() => {
      expect(screen.getByRole('button', { name: 'Selected DHL Express Domestic' })).toBeDisabled();
    });
  });

  it('blocks a replacement option until ambiguous selection is reconciled, then releases it', async () => {
    const replacementQuote = quoteForOrder('order-1', 'quote-2', 'option-2', 'DHL Express Replacement');
    listQuotes.mockResolvedValue([availableQuote, replacementQuote]);
    selectOption
      .mockRejectedValueOnce(new Error('response lost after commit'))
      .mockResolvedValueOnce({
        ...availableQuote,
        status: 'selected',
        selected_option_id: 'option-1',
      });
    render(<CustomerShippingQuotes orderId="order-1" />);

    fireEvent.click(await screen.findByRole('button', { name: 'Choose DHL Express Domestic' }));
    expect(await screen.findByText('Delivery options are unavailable right now. Please try again.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Choose DHL Express Replacement' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Choose DHL Express Domestic' }));

    await waitFor(() => expect(selectOption).toHaveBeenCalledTimes(2));
    expect(selectOption.mock.calls[0][3]).toBe(selectOption.mock.calls[1][3]);
    expect(await screen.findByRole('button', { name: 'Choose DHL Express Replacement' })).toBeEnabled();
  });

  it('ignores stale success from the previous order without clearing the new selection', async () => {
    const orderAQuote = quoteForOrder('order-a', 'quote-a', 'option-a', 'Order A Delivery');
    const orderBQuote = quoteForOrder('order-b', 'quote-b', 'option-b', 'Order B Delivery');
    const orderAResult = deferred<typeof orderAQuote>();
    const orderBResult = deferred<typeof orderBQuote>();
    listQuotes.mockImplementation((orderId: string) => Promise.resolve(orderId === 'order-a' ? [orderAQuote] : [orderBQuote]));
    selectOption.mockImplementation((orderId: string) => (orderId === 'order-a' ? orderAResult.promise : orderBResult.promise));
    const { rerender } = render(<CustomerShippingQuotes orderId="order-a" />);

    fireEvent.click(await screen.findByRole('button', { name: 'Choose Order A Delivery' }));
    rerender(<CustomerShippingQuotes orderId="order-b" />);
    fireEvent.click(await screen.findByRole('button', { name: 'Choose Order B Delivery' }));
    await act(async () => {
      orderAResult.resolve({ ...orderAQuote, status: 'selected', selected_option_id: 'option-a' });
      await orderAResult.promise;
    });

    expect(screen.getByRole('button', { name: 'Selecting…' })).toBeDisabled();
    expect(screen.queryByText('Delivery option selected.')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Selecting…' }));
    expect(selectOption).toHaveBeenCalledTimes(2);

    await act(async () => {
      orderBResult.resolve({ ...orderBQuote, status: 'selected', selected_option_id: 'option-b' });
      await orderBResult.promise;
    });
    expect(await screen.findByRole('button', { name: 'Selected Order B Delivery' })).toBeDisabled();
  });

  it('ignores stale failure from the previous order without corrupting the new selection', async () => {
    const orderAQuote = quoteForOrder('order-a', 'quote-a', 'option-a', 'Order A Delivery');
    const orderBQuote = quoteForOrder('order-b', 'quote-b', 'option-b', 'Order B Delivery');
    const orderAResult = deferred<typeof orderAQuote>();
    const orderBResult = deferred<typeof orderBQuote>();
    listQuotes.mockImplementation((orderId: string) => Promise.resolve(orderId === 'order-a' ? [orderAQuote] : [orderBQuote]));
    selectOption.mockImplementation((orderId: string) => (orderId === 'order-a' ? orderAResult.promise : orderBResult.promise));
    const { rerender } = render(<CustomerShippingQuotes orderId="order-a" />);

    fireEvent.click(await screen.findByRole('button', { name: 'Choose Order A Delivery' }));
    rerender(<CustomerShippingQuotes orderId="order-b" />);
    fireEvent.click(await screen.findByRole('button', { name: 'Choose Order B Delivery' }));
    await act(async () => {
      orderAResult.reject(new Error('late failure from order A'));
      await orderAResult.promise.catch(() => undefined);
    });

    expect(screen.getByRole('button', { name: 'Selecting…' })).toBeDisabled();
    expect(screen.queryByText(SAFE_ERROR)).not.toBeInTheDocument();

    await act(async () => {
      orderBResult.resolve({ ...orderBQuote, status: 'selected', selected_option_id: 'option-b' });
      await orderBResult.promise;
    });
    expect(await screen.findByRole('button', { name: 'Selected Order B Delivery' })).toBeDisabled();
  });

  it('disables expired quotes and never attempts selection', async () => {
    listQuotes.mockResolvedValue([{ ...availableQuote, status: 'expired' }]);
    render(<CustomerShippingQuotes orderId="order-1" />);

    const button = await screen.findByRole('button', { name: 'Expired DHL Express Domestic' });
    expect(button).toBeDisabled();
    fireEvent.click(button);
    expect(selectOption).not.toHaveBeenCalled();
  });

  it('retries loading after a list failure without creating a new quote', async () => {
    listQuotes.mockRejectedValueOnce(new Error('private backend detail')).mockResolvedValueOnce([availableQuote]);
    render(<CustomerShippingQuotes orderId="order-1" />);

    fireEvent.click(await screen.findByRole('button', { name: 'Retry loading delivery options' }));

    await waitFor(() => expect(listQuotes).toHaveBeenCalledTimes(2));
    expect(createQuote).not.toHaveBeenCalled();
    expect(await screen.findByText('DHL Express Domestic')).toBeInTheDocument();
  });

  it('reuses the same idempotency key after an ambiguous create failure', async () => {
    listQuotes.mockResolvedValue([]);
    createQuote
      .mockRejectedValueOnce(new Error('provider account 123; package hash secret'))
      .mockResolvedValueOnce(availableQuote);
    render(<CustomerShippingQuotes orderId="order-1" />);

    fireEvent.click(await screen.findByRole('button', { name: 'Get delivery options' }));
    expect(await screen.findByText('Delivery options are unavailable right now. Please try again.')).toBeInTheDocument();
    expect(screen.queryByText(/provider account|package hash|secret/i)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
    await waitFor(() => expect(createQuote).toHaveBeenCalledTimes(2));
    expect(createQuote.mock.calls[0][1]).toBe(createQuote.mock.calls[1][1]);
  });

  it('expires an available quote while the customer keeps the view open', async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2099-01-01T11:59:59Z'));
    listQuotes.mockResolvedValue([
      { ...availableQuote, expires_at: '2099-01-01T12:00:00Z' },
    ]);
    render(<CustomerShippingQuotes orderId="order-1" />);

    await vi.waitFor(() => {
      expect(screen.getByRole('button', { name: 'Choose DHL Express Domestic' })).toBeEnabled();
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });

    expect(screen.getByRole('button', { name: 'Expired DHL Express Domestic' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Get delivery options' })).toBeEnabled();
    expect(selectOption).not.toHaveBeenCalled();
    vi.useRealTimers();
  });
});
