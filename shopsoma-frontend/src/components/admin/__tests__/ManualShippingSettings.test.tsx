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
    resolveSave({});
    await waitFor(() => expect(onBusyChange).toHaveBeenLastCalledWith(false));
  });
});
