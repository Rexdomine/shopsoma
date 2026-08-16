import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { CheckoutEstimate } from '../../services/checkoutService';
import CheckoutEstimateSelector from './CheckoutEstimateSelector';

const estimate = (options = 1): CheckoutEstimate => ({
  id: 'estimate-1',
  order_id: 'order-1',
  currency: 'NGN',
  expires_at: '2099-08-15T12:00:00Z',
  server_payable_total: '12500.00',
  selected_option: null,
  options: Array.from({ length: options }, (_, index) => ({
    id: `option-${index + 1}`,
    option_key: `option-${index + 1}`,
    service_code: `service-${index + 1}`,
    service_label: index ? 'Priority delivery' : 'Standard delivery',
    amount: index ? '3500.00' : '2500.00',
    currency: 'NGN',
    min_delivery_days: index ? 1 : 3,
    max_delivery_days: index ? 2 : 5,
  })),
});

function renderSelector(overrides: Partial<React.ComponentProps<typeof CheckoutEstimateSelector>> = {}) {
  const selectOption = vi.fn().mockImplementation(async (_estimateId: string, optionId: string) => ({
    ...estimate(2),
    selected_option: estimate(2).options.find((option) => option.id === optionId) ?? null,
  }));
  const refreshEstimate = vi.fn().mockResolvedValue(estimate(2));
  const onSelectionConfirmed = vi.fn();
  render(
    <CheckoutEstimateSelector
      estimate={estimate(1)}
      selectOption={selectOption}
      refreshEstimate={refreshEstimate}
      onSelectionConfirmed={onSelectionConfirmed}
      {...overrides}
    />,
  );
  return { selectOption, refreshEstimate, onSelectionConfirmed };
}

describe('CheckoutEstimateSelector', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it.each([1, 2])('never auto-selects when the server returns %i option(s)', (count) => {
    const { selectOption, onSelectionConfirmed } = renderSelector({ estimate: estimate(count) });

    expect(selectOption).not.toHaveBeenCalled();
    expect(onSelectionConfirmed).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'Continue to payment' })).toBeDisabled();
    expect(screen.getAllByRole('button', { name: /^Select / })).toHaveLength(count);
  });

  it('shows amount, currency, delivery range and expiry, then enables Continue only after selection succeeds', async () => {
    let resolveSelection!: (value: CheckoutEstimate) => void;
    const pending = new Promise<CheckoutEstimate>((resolve) => {
      resolveSelection = resolve;
    });
    const selectOption = vi.fn().mockReturnValue(pending);
    const onSelectionConfirmed = vi.fn();
    renderSelector({ estimate: estimate(1), selectOption, onSelectionConfirmed });

    expect(screen.getByText('NGN 2,500.00')).toBeInTheDocument();
    expect(screen.getByText('3–5 business days')).toBeInTheDocument();
    expect(screen.getByText(/Expires/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Select Standard delivery' }));
    expect(screen.getByRole('button', { name: 'Continue to payment' })).toBeDisabled();

    resolveSelection({ ...estimate(1), selected_option: estimate(1).options[0] });
    await waitFor(() => expect(screen.getByRole('button', { name: 'Continue to payment' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: 'Continue to payment' }));
    expect(onSelectionConfirmed).toHaveBeenCalledWith(expect.objectContaining({ selected_option: expect.objectContaining({ id: 'option-1' }) }));
  });

  it.each(['expired', 'stale', 'stock'])('refreshes options after a %s 409 without silently selecting a replacement', async (reason) => {
    const conflict = { isAxiosError: true, response: { status: 409, data: { detail: `${reason} checkout estimate` } } };
    const selectOption = vi.fn().mockRejectedValue(conflict);
    const refreshEstimate = vi.fn().mockResolvedValue(estimate(2));
    const { onSelectionConfirmed } = renderSelector({ selectOption, refreshEstimate });

    fireEvent.click(screen.getByRole('button', { name: 'Select Standard delivery' }));

    expect(await screen.findByText(/Delivery options changed/)).toBeInTheDocument();
    expect(refreshEstimate).toHaveBeenCalledTimes(1);
    expect(onSelectionConfirmed).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'Continue to payment' })).toBeDisabled();
    expect(screen.getAllByRole('button', { name: /^Select / })).toHaveLength(2);
  });

  it('keeps a 503 retryable and never marks selection complete', async () => {
    const unavailable = { isAxiosError: true, response: { status: 503 } };
    const selectOption = vi.fn().mockRejectedValue(unavailable);
    const { refreshEstimate, onSelectionConfirmed } = renderSelector({ selectOption });

    fireEvent.click(screen.getByRole('button', { name: 'Select Standard delivery' }));

    expect(await screen.findByText(/temporarily unavailable/i)).toBeInTheDocument();
    expect(refreshEstimate).not.toHaveBeenCalled();
    expect(onSelectionConfirmed).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'Continue to payment' })).toBeDisabled();
  });

  it.each([404, 410])('handles terminal status %s from a conflict refresh without an unhandled rejection', async (status) => {
    const conflict = { isAxiosError: true, response: { status: 409 } };
    const terminal = { isAxiosError: true, response: { status } };
    const selectOption = vi.fn().mockRejectedValue(conflict);
    const refreshEstimate = vi.fn().mockRejectedValue(terminal);
    const { onSelectionConfirmed } = renderSelector({ selectOption, refreshEstimate });

    fireEvent.click(screen.getByRole('button', { name: 'Select Standard delivery' }));

    expect(await screen.findByText(/Checkout access expired/i)).toBeInTheDocument();
    expect(refreshEstimate).toHaveBeenCalledTimes(1);
    expect(onSelectionConfirmed).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'Continue to payment' })).toBeDisabled();
  });
});
