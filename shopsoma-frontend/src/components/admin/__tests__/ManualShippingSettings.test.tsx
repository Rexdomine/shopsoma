import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ManualShippingSettings from '../ManualShippingSettings';
import { getManualShippingRates } from '../../../services/settingsService';

vi.mock('../../../services/settingsService', () => ({
  getManualShippingRates: vi.fn(),
  saveManualShippingRate: vi.fn(),
  deactivateManualShippingRate: vi.fn(),
  setDefaultManualShippingRate: vi.fn(),
  previewManualShippingRates: vi.fn(),
}));

describe('ManualShippingSettings', () => {
  beforeEach(() => {
    vi.mocked(getManualShippingRates).mockResolvedValue([]);
    vi.stubGlobal('confirm', vi.fn());
  });

  it('uses Nigerian state selectors for rate setup and quote preview', async () => {
    render(<ManualShippingSettings />);
    await waitFor(() => expect(screen.getByRole('button', { name: /add shipping rate/i })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /add shipping rate/i }));

    const rateState = screen.getByRole('combobox', { name: 'State (blank for all)' });
    expect(screen.getAllByRole('option', { name: 'Lagos' })).toHaveLength(2);
    fireEvent.change(rateState, { target: { value: 'Lagos' } });
    expect(rateState).toHaveValue('Lagos');
    expect(screen.getByRole('combobox', { name: 'Preview state' })).toHaveValue('Lagos');
  });

  it('checks current dirty state when Escape is pressed after an edit', async () => {
    render(<ManualShippingSettings />);
    await waitFor(() => expect(screen.getByRole('button', { name: /add shipping rate/i })).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: /add shipping rate/i }));
    fireEvent.change(screen.getByLabelText('Rate name'), { target: { value: 'Lagos delivery' } });
    fireEvent.keyDown(document, { key: 'Escape' });

    expect(window.confirm).toHaveBeenCalledWith('Discard unsaved shipping rate edits?');
    expect(screen.getByRole('dialog')).toBeInTheDocument();

    vi.mocked(window.confirm).mockReturnValue(true);
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('reports save busy state until the request completes', async () => {
    let resolveSave!: (value: unknown) => void;
    const pending = new Promise<unknown>(resolve => { resolveSave = resolve; });
    const { saveManualShippingRate } = await import('../../../services/settingsService');
    vi.mocked(saveManualShippingRate).mockReturnValue(pending as Promise<any>);
    const onBusyChange = vi.fn();
    render(<ManualShippingSettings onBusyChange={onBusyChange} />);
    await waitFor(() => expect(screen.getByRole('button', { name: /add shipping rate/i })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /add shipping rate/i }));
    fireEvent.change(screen.getByLabelText('Rate name'), { target: { value: 'Lagos delivery' } });
    fireEvent.click(screen.getByRole('button', { name: /save shipping rate/i }));
    await waitFor(() => expect(onBusyChange).toHaveBeenCalledWith(true));
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    resolveSave({});
    await waitFor(() => expect(onBusyChange).toHaveBeenLastCalledWith(false));
  });

  it('reports save errors inside the open dialog', async () => {
    const { saveManualShippingRate } = await import('../../../services/settingsService');
    vi.mocked(saveManualShippingRate).mockRejectedValue(new Error('save failed'));
    render(<ManualShippingSettings />);
    await waitFor(() => expect(screen.getByRole('button', { name: /add shipping rate/i })).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: /add shipping rate/i }));
    fireEvent.change(screen.getByLabelText('Rate name'), { target: { value: 'Lagos delivery' } });
    fireEvent.click(screen.getByRole('button', { name: /save shipping rate/i }));

    await waitFor(() => expect(screen.getByRole('dialog').querySelector('[role="alert"]')).toHaveTextContent(/unable to save/i));
  });

  it('preserves a legacy FCT rate value while it is being edited', async () => {
    vi.mocked(getManualShippingRates).mockResolvedValue([{
      id: 'rate-fct', name: 'FCT delivery', description: '', country: 'Nigeria', state: 'FCT',
      base_rate: 1500, min_order_value: 0, max_order_value: null, min_delivery_days: 2, max_delivery_days: 5,
      is_active: true, is_default: false, priority: 1,
    }]);
    render(<ManualShippingSettings />);
    await waitFor(() => expect(screen.getByRole('button', { name: 'Edit FCT delivery' })).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: 'Edit FCT delivery' }));
    expect(screen.getByRole('combobox', { name: 'State (blank for all)' })).toHaveValue('FCT');
    expect(screen.getByRole('option', { name: 'FCT (legacy)' })).toBeInTheDocument();
  });

  it('keeps rate ordering metadata visible in the saved-rate list', async () => {
    vi.mocked(getManualShippingRates).mockResolvedValue([{
      id: 'rate-1', name: 'Lagos delivery', description: '', country: 'Nigeria', state: 'Lagos',
      base_rate: 1500, min_order_value: 0, max_order_value: null, min_delivery_days: 2, max_delivery_days: 5,
      is_active: true, is_default: true, priority: 3,
    }]);
    render(<ManualShippingSettings />);

    await waitFor(() => expect(screen.getByText(/Priority 3 · Default · Active/)).toBeInTheDocument());
  });
});
