import { act, render, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import ComingSoon from './ComingSoon';

const getComingSoonSettings = vi.hoisted(() => vi.fn());

vi.mock('../services/settingsService', () => ({
  getComingSoonSettings,
}));

describe('ComingSoon', () => {
  it('releases the parent when a follow-up settings read reports the gate is open', async () => {
    getComingSoonSettings.mockResolvedValue({
      enabled: false,
      launch_at: null,
      image_url: '/campaign.webp',
    });
    const onReleased = vi.fn();

    render(<ComingSoon onReleased={onReleased} />);

    await waitFor(() => expect(onReleased).toHaveBeenCalledTimes(1));
  });

  it('polls an open-ended gate and releases when an administrator disables it', async () => {
    vi.useFakeTimers();
    getComingSoonSettings
      .mockResolvedValueOnce({ enabled: true, launch_at: null, image_url: '/campaign.webp' })
      .mockResolvedValueOnce({ enabled: false, launch_at: null, image_url: '/campaign.webp' });
    const onReleased = vi.fn();

    render(<ComingSoon onReleased={onReleased} />);
    await act(async () => { await Promise.resolve(); });
    await act(async () => { vi.advanceTimersByTime(10_000); await Promise.resolve(); });

    expect(onReleased).toHaveBeenCalledTimes(1);
    vi.useRealTimers();
  });
});
