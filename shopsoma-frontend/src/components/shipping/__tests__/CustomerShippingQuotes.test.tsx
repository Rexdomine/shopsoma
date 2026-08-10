import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import CustomerShippingQuotes from '../CustomerShippingQuotes';

const { listQuotes, createQuote, selectOption } = vi.hoisted(() => ({
  listQuotes: vi.fn(),
  createQuote: vi.fn(),
  selectOption: vi.fn(),
}));

vi.mock('../../../services/shippingQuoteService', () => ({
  shippingQuoteService: { listQuotes, createQuote, selectOption },
}));

const availableQuote = {
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

describe('CustomerShippingQuotes', () => {
  beforeEach(() => {
    listQuotes.mockReset();
    createQuote.mockReset();
    selectOption.mockReset();
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
