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

  it('links the Instagram icon to the official ShopSoma Africa profile', async () => {
    getComingSoonSettings.mockResolvedValue({
      enabled: true,
      launch_at: null,
      image_url: '/campaign.webp',
    });

    const { getByRole } = render(<ComingSoon />);

    await waitFor(() => expect(getByRole('link', { name: 'ShopSoma on Instagram' })).toHaveAttribute(
      'href',
      'https://www.instagram.com/shopsoma.africa?stkn=N3E1dndjZTBsajdk',
    ));
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

  it('keeps a confirmed closed gate when the duplicate read fails', async () => {
    getComingSoonSettings.mockRejectedValueOnce(new Error('temporary outage'));
    const onReleased = vi.fn();

    render(
      <ComingSoon
        initialSettings={{ enabled: true, launch_at: null, image_url: '/campaign.webp' }}
        onReleased={onReleased}
      />,
    );

    await waitFor(() => expect(getComingSoonSettings).toHaveBeenCalledTimes(1));
    expect(onReleased).not.toHaveBeenCalled();
    expect(document.querySelector('main')).toBeInTheDocument();
  });

  it('does not poll settings while an enabled gate has no launch time', async () => {
    vi.useFakeTimers();
    getComingSoonSettings.mockRejectedValue(new Error('temporary outage'));

    render(
      <ComingSoon
        initialSettings={{ enabled: true, launch_at: null, image_url: '/campaign.webp' }}
      />,
    );

    await act(async () => { await Promise.resolve(); });
    expect(getComingSoonSettings).toHaveBeenCalledTimes(1);

    await act(async () => { vi.advanceTimersByTime(60_000); });
    expect(getComingSoonSettings).toHaveBeenCalledTimes(1);
  });

  it('refreshes displayed settings when the parent provides a newer snapshot', async () => {
    getComingSoonSettings.mockRejectedValue(new Error('temporary outage'));
    const view = render(
      <ComingSoon
        initialSettings={{ enabled: true, launch_at: null, image_url: '/campaign-old.webp' }}
      />,
    );

    await waitFor(() => expect(getComingSoonSettings).toHaveBeenCalledTimes(1));
    view.rerender(
      <ComingSoon
        initialSettings={{ enabled: true, launch_at: null, image_url: '/campaign-new.webp' }}
      />,
    );

    await waitFor(() => expect(view.getByAltText('ShopSoma campaign storefront')).toHaveAttribute('src', '/campaign-new.webp'));
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

  it('retries a failed launch revalidation with bounded backoff', async () => {
    vi.useFakeTimers();
    const launchAt = new Date(Date.now() - 1_000).toISOString();
    getComingSoonSettings
      .mockResolvedValueOnce({ enabled: true, launch_at: launchAt, image_url: '/campaign.webp' })
      .mockRejectedValueOnce(new Error('temporary outage'))
      .mockResolvedValueOnce({ enabled: false, launch_at: null, image_url: '/campaign.webp' });
    const onReleased = vi.fn();

    render(<ComingSoon onReleased={onReleased} />);
    await act(async () => { await Promise.resolve(); });
    await act(async () => { vi.advanceTimersByTime(1_000); await Promise.resolve(); });
    expect(getComingSoonSettings).toHaveBeenCalledTimes(2);

    await act(async () => { vi.advanceTimersByTime(5_000); await Promise.resolve(); });
    expect(getComingSoonSettings).toHaveBeenCalledTimes(3);
    expect(onReleased).toHaveBeenCalledTimes(1);
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
