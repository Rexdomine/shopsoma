import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import AdminSettings from './AdminSettings';

const mocks = vi.hoisted(() => ({
  getManualShippingRates: vi.fn(), saveManualShippingRate: vi.fn(),
  deactivateManualShippingRate: vi.fn(), setDefaultManualShippingRate: vi.fn(),
  previewManualShippingRates: vi.fn(), updateShippingProviderSettings: vi.fn(),
}));
vi.mock('../../components/admin/AdminSidebar', () => ({ default: () => null }));
vi.mock('../../hooks/useCurrency', () => ({ useCurrency: () => ({ fetchExchangeRate: vi.fn() }) }));
vi.mock('../../services/settingsService', () => ({
  ...mocks,
  getExchangeRate: vi.fn(async () => ({ rate: 1600 })),
  getShippingProviderSettings: vi.fn(async () => ({ provider: 'manual', readiness: { manual: true, shipbubble: false, dhl: false } })),
  getPayoutHoldSettings: vi.fn(async () => ({ hold_days: 14 })),
  getCommissionSettings: vi.fn(async () => ({ commission_rate: 10 })),
  getAdminFeaturedRotationSettings: vi.fn(async () => ({ rotation_minutes: 15 })),
  updateExchangeRate: vi.fn(), updatePayoutHoldSettings: vi.fn(), updateCommissionSettings: vi.fn(),
  updateFeaturedRotationSettings: vi.fn(), syncRenderDatabase: vi.fn(),
}));
const saved = { id: 'rate-1', name: 'Free Lagos', country: 'Nigeria', state: 'Lagos', base_rate: 0, description: '', min_order_value: 0, max_order_value: null, min_delivery_days: 2, max_delivery_days: 5, is_active: true, is_default: true, priority: 0 };
beforeEach(() => { window.history.replaceState(null, '', window.location.pathname); vi.restoreAllMocks(); vi.clearAllMocks(); mocks.getManualShippingRates.mockResolvedValue([]); });

it('saves a genuine zero rate, reloads persisted values, previews and deactivates it', async () => {
  render(<AdminSettings />);
  fireEvent.click(await screen.findByRole('button', { name: /Manual rates/ }));
  await screen.findByText('No manual rates configured. Add an active rate before accepting orders.');
  fireEvent.click(await screen.findByRole('button', { name: 'Add shipping rate' }));
  fireEvent.change(screen.getByLabelText('Rate name'), { target: { value: 'Free Lagos' } });
  fireEvent.change(screen.getByLabelText('State (blank for all)'), { target: { value: 'Lagos' } });
  mocks.saveManualShippingRate.mockResolvedValue(saved);
  mocks.getManualShippingRates.mockResolvedValue([saved]);
  fireEvent.click(screen.getByRole('button', { name: 'Save shipping rate' }));
  await screen.findByText('Shipping rate saved and reloaded.');
  expect(mocks.saveManualShippingRate).toHaveBeenCalledWith(expect.objectContaining({ base_rate: 0, name: 'Free Lagos', state: 'Lagos' }), undefined);
  await screen.findByRole('button', { name: 'Edit Free Lagos' });
  mocks.previewManualShippingRates.mockResolvedValue({ available_rates: [saved] });
  fireEvent.click(screen.getByRole('button', { name: 'Preview shipping' }));
  await screen.findByLabelText('Preview results');
  expect(mocks.previewManualShippingRates).toHaveBeenCalledWith({ country: 'Nigeria', state: 'Lagos', order_value: 60000 });
  mocks.deactivateManualShippingRate.mockResolvedValue(undefined);
  mocks.getManualShippingRates.mockResolvedValue([{ ...saved, is_active: false, is_default: false }]);
  fireEvent.click(screen.getByRole('button', { name: 'Deactivate Free Lagos' }));
  await screen.findByText('Rate deactivated. Issued quotes are unchanged.');
  expect(screen.queryByRole('button', { name: 'Deactivate Free Lagos' })).not.toBeInTheDocument();
});

it('hydrates edits and rejects crossed ranges without submitting; displays save failures', async () => {
  mocks.getManualShippingRates.mockResolvedValue([saved]);
  render(<AdminSettings />);
  fireEvent.click(await screen.findByRole('button', { name: /Manual rates/ }));
  fireEvent.click(await screen.findByRole('button', { name: 'Edit Free Lagos' }));
  expect(screen.getByLabelText('Price (NGN)')).toHaveValue(0);
  fireEvent.change(screen.getByLabelText('Minimum delivery days'), { target: { value: '9' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save shipping rate' }));
  await screen.findByRole('alert');
  expect(mocks.saveManualShippingRate).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText('Minimum delivery days'), { target: { value: '3' } });
  mocks.saveManualShippingRate.mockRejectedValue(new Error('offline'));
  fireEvent.click(screen.getByRole('button', { name: 'Save shipping rate' }));
  await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Unable to save or load'));
  expect(screen.getByLabelText('Rate name')).toHaveValue('Free Lagos');
});

it('keeps DHL disabled when sandbox readiness lacks secure-checkout routing', async () => {
  const { getShippingProviderSettings } = await import('../../services/settingsService');
  vi.mocked(getShippingProviderSettings).mockResolvedValue({
    provider: 'manual',
    use_shipbubble: false,
    readiness: { manual: true, shipbubble: false, dhl: true },
    checkout_estimates_required: false,
  });
  render(<AdminSettings />);
  fireEvent.click(await screen.findByRole('button', { name: /Shipping/ }));
  expect(await screen.findByRole('option', { name: 'DHL' })).toBeDisabled();
});

it('switches between focused settings workspaces', async () => {
  render(<AdminSettings />);
  const rates = await screen.findByRole('button', { name: /Manual rates/ });
  expect(screen.getByRole('heading', { name: 'Exchange rate' })).toBeInTheDocument();
  fireEvent.click(rates);
  expect(await screen.findByRole('heading', { name: 'Manual shipping rates' })).toBeInTheDocument();
  expect(rates).toHaveAttribute('aria-current', 'page');
});

it('clears manual-rate dirtiness after confirming a category switch', async () => {
  render(<AdminSettings />);
  fireEvent.click(await screen.findByRole('button', { name: /Manual rates/ }));
  fireEvent.click(await screen.findByRole('button', { name: 'Add shipping rate' }));
  fireEvent.change(screen.getByLabelText('Rate name'), { target: { value: 'Draft rate' } });
  vi.spyOn(window, 'confirm').mockReturnValue(true);
  fireEvent.click(screen.getByRole('button', { name: /Shipping/ }));
  expect(await screen.findByRole('heading', { name: 'Shipping provider' })).toBeInTheDocument();
  vi.mocked(window.confirm).mockClear();
  fireEvent.click(screen.getByRole('button', { name: /Manual rates/ }));
  fireEvent.click(screen.getByRole('button', { name: /Exchange rate/ }));
  expect(window.confirm).not.toHaveBeenCalled();
});

it('traps Tab in both directions and preserves a draft when cancelled', async () => {
  render(<AdminSettings />);
  fireEvent.click(await screen.findByRole('button', { name: /Manual rates/ }));
  fireEvent.click(await screen.findByRole('button', { name: 'Add shipping rate' }));
  const dialog = screen.getByRole('dialog');
  const first = screen.getByLabelText('Rate name');
  const last = screen.getByRole('button', { name: 'Cancel' });
  expect(document.activeElement).toBe(first);
  last.focus();
  fireEvent.keyDown(document, { key: 'Tab' });
  expect(document.activeElement).toBe(first);
  first.focus();
  fireEvent.keyDown(document, { key: 'Tab', shiftKey: true });
  expect(document.activeElement).toBe(last);
  fireEvent.change(first, { target: { value: 'Keep this draft' } });
  vi.spyOn(window, 'confirm').mockReturnValue(false);
  fireEvent.click(last);
  expect(dialog).toBeInTheDocument();
  expect(screen.getByLabelText('Rate name')).toHaveValue('Keep this draft');
});

it('restores preview constraints and renders returned price and ETA', async () => {
  render(<AdminSettings />);
  fireEvent.click(await screen.findByRole('button', { name: /Manual rates/ }));
  expect(screen.getByLabelText('Preview country')).toBeRequired();
  expect(screen.getByLabelText('Preview state')).toBeRequired();
  const subtotal = screen.getByLabelText('Preview subtotal (NGN)');
  expect(subtotal).toHaveAttribute('type', 'number');
  expect(subtotal).toHaveAttribute('min', '0.01');
  expect(subtotal).toHaveAttribute('step', '0.01');
  mocks.previewManualShippingRates.mockResolvedValue({ available_rates: [{ ...saved, base_rate: 1250, min_delivery_days: 3, max_delivery_days: 6 }] });
  fireEvent.click(screen.getByRole('button', { name: 'Preview shipping' }));
  expect(await screen.findByText(/NGN 1250\.00 · 3–6 business days/)).toBeInTheDocument();
});

it('marks an empty exchange rate as dirty so it cannot silently bypass discard protection', async () => {
  render(<AdminSettings />);
  const input = await screen.findByRole('spinbutton');
  fireEvent.change(input, { target: { value: '' } });
  expect(screen.getByText('Draft edits pending')).toBeInTheDocument();
  vi.spyOn(window, 'confirm').mockReturnValue(false);
  fireEvent.click(screen.getByRole('button', { name: /Manual rates/ }));
  expect(screen.getByRole('heading', { name: 'Exchange rate' })).toBeInTheDocument();
  expect(window.confirm).toHaveBeenCalled();
});

it('routes browser hash navigation through the guarded transition', async () => {
  render(<AdminSettings />);
  await screen.findByRole('heading', { name: 'Exchange rate' });
  fireEvent.change(screen.getByRole('spinbutton'), { target: { value: '1700' } });
  vi.spyOn(window, 'confirm').mockReturnValue(false);
  window.history.pushState(null, '', '#shipping');
  window.dispatchEvent(new HashChangeEvent('hashchange'));
  expect(screen.getByRole('heading', { name: 'Exchange rate' })).toBeInTheDocument();
  expect(window.confirm).toHaveBeenCalled();
});

it('restores the current hash when popstate navigation is rejected', async () => {
  render(<AdminSettings />);
  await screen.findByRole('heading', { name: 'Exchange rate' });
  fireEvent.change(screen.getByRole('spinbutton'), { target: { value: '1700' } });
  vi.spyOn(window, 'confirm').mockReturnValue(false);
  window.history.pushState(null, '', '#shipping');
  window.dispatchEvent(new PopStateEvent('popstate'));
  expect(screen.getByRole('heading', { name: 'Exchange rate' })).toBeInTheDocument();
  expect(window.location.hash).toBe('#currency');
});

it('reverses rejected indexed history navigation instead of overwriting the destination entry', async () => {
  render(<AdminSettings />);
  await screen.findByRole('heading', { name: 'Exchange rate' });
  fireEvent.change(screen.getByRole('spinbutton'), { target: { value: '1700' } });
  vi.spyOn(window, 'confirm').mockReturnValue(false);
  window.history.replaceState({ settingsHistoryIndex: 0 }, '', '#currency');
  window.history.pushState({ settingsHistoryIndex: -1 }, '', '#shipping');
  const go = vi.spyOn(window.history, 'go').mockImplementation(() => {});

  window.dispatchEvent(new PopStateEvent('popstate'));

  expect(go).toHaveBeenCalledWith(1);
  expect(window.history.state).toEqual({ settingsHistoryIndex: -1 });
});

it('restores the settings URL when rejecting navigation to a non-settings entry', async () => {
  window.history.replaceState(null, '', '/admin/settings#rates');
  render(<AdminSettings />);
  fireEvent.click(await screen.findByRole('button', { name: 'Add shipping rate' }));
  fireEvent.change(screen.getByLabelText('Rate name'), { target: { value: 'Keep this draft' } });
  vi.spyOn(window, 'confirm').mockReturnValue(false);

  window.history.pushState(null, '', '/admin/dashboard');
  window.dispatchEvent(new PopStateEvent('popstate'));

  expect(screen.getByRole('heading', { name: 'Manual shipping rates' })).toBeInTheDocument();
  expect(window.location.pathname).toBe('/admin/settings');
  expect(window.location.hash).toBe('#rates');
  expect(window.confirm).toHaveBeenCalled();
});

it('stops the router from committing a rejected non-settings popstate', async () => {
  window.history.replaceState({ idx: 3 }, '', '/admin/settings#rates');
  render(<AdminSettings />);
  fireEvent.click(await screen.findByRole('button', { name: 'Add shipping rate' }));
  fireEvent.change(screen.getByLabelText('Rate name'), { target: { value: 'Keep this draft' } });
  vi.spyOn(window, 'confirm').mockReturnValue(false);

  window.history.replaceState({ idx: 2 }, '', '/admin/dashboard');
  const go = vi.spyOn(window.history, 'go').mockImplementation(() => {});
  const event = new PopStateEvent('popstate');
  const stopImmediatePropagation = vi.spyOn(event, 'stopImmediatePropagation');
  window.dispatchEvent(event);

  expect(stopImmediatePropagation).toHaveBeenCalled();
  expect(go).toHaveBeenCalledWith(1);
  expect(screen.getByRole('heading', { name: 'Manual shipping rates' })).toBeInTheDocument();
});

it('handles one browser traversal once when both history events are emitted', async () => {
  render(<AdminSettings />);
  await screen.findByRole('heading', { name: 'Exchange rate' });
  fireEvent.change(screen.getByRole('spinbutton'), { target: { value: '1700' } });
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);

  window.history.pushState(null, '', '#shipping');
  window.dispatchEvent(new PopStateEvent('popstate'));
  window.dispatchEvent(new HashChangeEvent('hashchange'));

  expect(confirm).toHaveBeenCalledTimes(1);
  expect(screen.getByRole('heading', { name: 'Exchange rate' })).toBeInTheDocument();
});

it('blocks category transitions while any settings save is in flight', async () => {
  let resolveSave!: (value: any) => void;
  const save = new Promise<any>((resolve) => { resolveSave = resolve; });
  const { updateExchangeRate } = await import('../../services/settingsService');
  vi.mocked(updateExchangeRate).mockReturnValue(save);
  render(<AdminSettings />);
  const input = await screen.findByRole('spinbutton');
  fireEvent.change(input, { target: { value: '1700' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));
  fireEvent.click(screen.getByRole('button', { name: /Manual rates/ }));
  expect(screen.getByRole('heading', { name: 'Exchange rate' })).toBeInTheDocument();
  expect(screen.getByText('Please wait for the current save to finish before switching categories.')).toBeInTheDocument();
  resolveSave({ rate: 1700 });
});
