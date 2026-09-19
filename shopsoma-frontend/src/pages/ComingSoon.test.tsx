import { act, cleanup, render, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import ComingSoon from './ComingSoon';

const getComingSoonSettings = vi.hoisted(() => vi.fn());

vi.mock('../services/settingsService', () => ({
  getComingSoonSettings,
}));

beforeEach(() => {
  getComingSoonSettings.mockReset();
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe('ComingSoon', () => {
  it('shows an explicit loading state while the launch settings request is pending', () => {
    getComingSoonSettings.mockReturnValue(new Promise(() => {}));

    const { getByRole } = render(<ComingSoon />);

    expect(getByRole('status')).toHaveTextContent('Loading launch settings…');
  });

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

  it('revalidates an expired launch time only once while the server keeps the gate enabled', async () => {
    vi.useFakeTimers();
    const launchAt = new Date(Date.now() - 1_000).toISOString();
    getComingSoonSettings
      .mockResolvedValueOnce({ enabled: true, launch_at: launchAt, image_url: '/campaign.webp' })
      .mockResolvedValue({ enabled: true, launch_at: launchAt, image_url: '/campaign.webp' });

    render(<ComingSoon />);
    await act(async () => { await Promise.resolve(); });
    await act(async () => { vi.advanceTimersByTime(5_000); await Promise.resolve(); });

    expect(getComingSoonSettings).toHaveBeenCalledTimes(2);
    vi.useRealTimers();
  });

  it('revalidates a scheduled gate before releasing after the local countdown', async () => {
    vi.useFakeTimers();
    const launchAt = new Date(Date.now() + 1_000).toISOString();
    getComingSoonSettings
      .mockResolvedValueOnce({ enabled: true, launch_at: launchAt, image_url: '/campaign.webp' })
      .mockResolvedValueOnce({ enabled: false, launch_at: null, image_url: '/campaign.webp' });
    const onReleased = vi.fn();

    render(<ComingSoon onReleased={onReleased} />);
    await act(async () => { await Promise.resolve(); });
    await act(async () => { vi.advanceTimersByTime(1_000); await Promise.resolve(); });

    expect(getComingSoonSettings).toHaveBeenCalledTimes(2);
    expect(onReleased).toHaveBeenCalledTimes(1);
    vi.useRealTimers();
  });
});
