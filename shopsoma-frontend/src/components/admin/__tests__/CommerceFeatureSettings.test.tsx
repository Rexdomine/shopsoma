import { beforeEach, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import CommerceFeatureSettings from '../CommerceFeatureSettings';
import { getCommerceFeatures, updateCommerceFeatures } from '../../../services/settingsService';
vi.mock('../../../services/settingsService', () => ({ getCommerceFeatures: vi.fn(), updateCommerceFeatures: vi.fn() }));
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(getCommerceFeatures).mockResolvedValue({ stripe_enabled: false, usd_switching_enabled: false });
});
it('loads saved state and changes the two flags independently, then reloads persistence', async () => {
  const view = render(<CommerceFeatureSettings />);
  const stripe = screen.getByLabelText('Stripe payments enabled');
  expect(stripe).toBeDisabled();
  await waitFor(() => expect(stripe).toBeEnabled());
  vi.mocked(updateCommerceFeatures).mockResolvedValueOnce({ stripe_enabled: true, usd_switching_enabled: false });
  fireEvent.click(stripe);
  await waitFor(() => expect(stripe).toBeChecked());
  expect(updateCommerceFeatures).toHaveBeenLastCalledWith({ stripe_enabled: true, usd_switching_enabled: false });
  vi.mocked(updateCommerceFeatures).mockResolvedValueOnce({ stripe_enabled: true, usd_switching_enabled: true });
  fireEvent.click(screen.getByLabelText('USD currency switching enabled'));
  await waitFor(() => expect(screen.getByLabelText('USD currency switching enabled')).toBeChecked());
  expect(updateCommerceFeatures).toHaveBeenLastCalledWith({ stripe_enabled: true, usd_switching_enabled: true });
  view.unmount();
  vi.mocked(getCommerceFeatures).mockResolvedValueOnce({ stripe_enabled: true, usd_switching_enabled: true });
  render(<CommerceFeatureSettings />);
  await waitFor(() => expect(screen.getByLabelText('Stripe payments enabled')).toBeChecked());
});
it('keeps controls disabled on load failure and recovers on reload', async () => {
  vi.mocked(getCommerceFeatures).mockRejectedValueOnce(new Error('offline'));
  render(<CommerceFeatureSettings />);
  await screen.findByRole('alert');
  expect(screen.getByLabelText('Stripe payments enabled')).toBeDisabled();
  fireEvent.click(screen.getByRole('button', { name: 'Reload settings' }));
  await waitFor(() => expect(screen.getByLabelText('Stripe payments enabled')).toBeEnabled());
});
it('does not claim a failed save succeeded', async () => {
  vi.mocked(updateCommerceFeatures).mockRejectedValueOnce(new Error('forbidden'));
  render(<CommerceFeatureSettings />);
  await waitFor(() => expect(screen.getByLabelText('Stripe payments enabled')).toBeEnabled());
  fireEvent.click(screen.getByLabelText('Stripe payments enabled'));
  await screen.findByRole('alert');
  expect(screen.getByLabelText('Stripe payments enabled')).not.toBeChecked();
  expect(screen.getByLabelText('Stripe payments enabled')).toBeDisabled();
});
