import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import CheckoutHoldSettings from '../CheckoutHoldSettings';

const mocks = vi.hoisted(() => ({
  getAdminCheckoutHoldSettings: vi.fn(),
  updateCheckoutHoldSettings: vi.fn(),
}));

vi.mock('../../../services/settingsService', () => ({
  getAdminCheckoutHoldSettings: mocks.getAdminCheckoutHoldSettings,
  updateCheckoutHoldSettings: mocks.updateCheckoutHoldSettings,
}));

describe('CheckoutHoldSettings', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.getAdminCheckoutHoldSettings.mockResolvedValue({
      reservation_ttl_minutes: 30,
      authorization_grace_minutes: 15,
      release_on_payment_close: false,
      updated_at: null,
    });
  });

  it('loads and displays default checkout hold settings', async () => {
    render(<CheckoutHoldSettings />);

    expect(await screen.findByRole('heading', { name: 'Checkout stock holds' })).toBeInTheDocument();
    expect(screen.getByText('45 minutes')).toBeInTheDocument();
    expect(screen.getByLabelText(/Stock reservation hold \(minutes\)/i)).toHaveValue(30);
    expect(screen.getByLabelText(/Payment authorization grace \(minutes\)/i)).toHaveValue(15);
    expect(
      screen.getByLabelText(/Release stock when Paystack modal is closed without paying/i),
    ).not.toBeChecked();
  });

  it('saves updated timers and modal-close release flag', async () => {
    mocks.updateCheckoutHoldSettings.mockResolvedValueOnce({
      reservation_ttl_minutes: 10,
      authorization_grace_minutes: 2,
      release_on_payment_close: true,
      updated_at: '2026-11-21T19:00:00Z',
    });

    render(<CheckoutHoldSettings />);
    const ttlInput = await screen.findByLabelText(/Stock reservation hold \(minutes\)/i);
    const graceInput = screen.getByLabelText(/Payment authorization grace \(minutes\)/i);
    const closeCheckbox = screen.getByLabelText(
      /Release stock when Paystack modal is closed without paying/i,
    );

    fireEvent.change(ttlInput, { target: { value: '10' } });
    fireEvent.change(graceInput, { target: { value: '2' } });
    fireEvent.click(closeCheckbox);
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));

    await waitFor(() => {
      expect(mocks.updateCheckoutHoldSettings).toHaveBeenCalledWith({
        reservation_ttl_minutes: 10,
        authorization_grace_minutes: 2,
        release_on_payment_close: true,
      });
    });
    expect(await screen.findByText('12 minutes')).toBeInTheDocument();
  });

  it('rejects out-of-range inputs without submitting', async () => {
    render(<CheckoutHoldSettings />);
    const ttlInput = await screen.findByLabelText(/Stock reservation hold \(minutes\)/i);
    const graceInput = screen.getByLabelText(/Payment authorization grace \(minutes\)/i);

    fireEvent.change(ttlInput, { target: { value: '0' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));
    expect(mocks.updateCheckoutHoldSettings).not.toHaveBeenCalled();

    fireEvent.change(ttlInput, { target: { value: '31' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));
    expect(mocks.updateCheckoutHoldSettings).not.toHaveBeenCalled();

    fireEvent.change(ttlInput, { target: { value: '15' } });
    fireEvent.change(graceInput, { target: { value: '16' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));
    expect(mocks.updateCheckoutHoldSettings).not.toHaveBeenCalled();
  });

  it('restores loaded values on Discard edits', async () => {
    render(<CheckoutHoldSettings />);
    const ttlInput = await screen.findByLabelText(/Stock reservation hold \(minutes\)/i);

    fireEvent.change(ttlInput, { target: { value: '8' } });
    expect(ttlInput).toHaveValue(8);

    fireEvent.click(screen.getByRole('button', { name: 'Discard edits' }));
    expect(ttlInput).toHaveValue(30);
    expect(screen.getByRole('button', { name: 'Save changes' })).toBeDisabled();
  });
});
