import { beforeEach, describe, expect, it, vi } from 'vitest';

const { get, post } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock('../api', () => ({ default: { get, post } }));
import * as service from '../adminOrderService';

describe('admin DHL operation contracts', () => {
  beforeEach(() => { vi.resetAllMocks(); });

  it('books the exact supplied package, version, seal and intent with the caller key', async () => {
    const payload = { intent_id: 'intent-1', package_id: 'package-2', package_version: 3,
      seal_id: 'seal-3', idempotency_key: 'booking-key' };
    const result = { booking_id: 'booking-1', result_kind: 'unknown' };
    post.mockResolvedValue({ data: result });
    expect(await service.createDhlBooking('order-1', payload)).toEqual(result);
    expect(post).toHaveBeenCalledWith('/admin/orders/order-1/dhl/bookings', payload, { timeout: 30000 });
  });

  it('downloads the label as binary through the authenticated API client', async () => {
    const blob = new Blob(['label'], { type: 'application/pdf' });
    get.mockResolvedValue({ data: blob });
    expect(await service.getDhlLabel('order-1', 'booking-1')).toBe(blob);
    expect(get).toHaveBeenCalledWith('/admin/orders/order-1/dhl/bookings/booking-1/label', { responseType: 'blob', timeout: 30000 });
  });

  it('records handoff using the exact private evidence and timestamp contract', async () => {
    const payload = { occurred_at: '2026-09-28T10:00:00Z', idempotency_key: 'handoff-key',
      counterparty: 'DHL', evidence_ref: 'custody/evidence-1', evidence_sha256: 'a'.repeat(64) };
    const result = { booking_id: 'booking-1', outbound_state: 'tendered' };
    post.mockResolvedValue({ data: result });
    expect(await service.recordDhlHandoff('order-1', 'booking-1', payload)).toEqual(result);
    expect(post).toHaveBeenCalledWith('/admin/orders/order-1/dhl/bookings/booking-1/handoff', payload, { timeout: 30000 });
  });

  it('refreshes tracking for the specified booking and caller key', async () => {
    const payload = { booking_id: 'booking-1', idempotency_key: 'tracking-key' };
    const result = { observations_recorded: 0 };
    post.mockResolvedValue({ data: result });
    expect(await service.refreshDhlTracking('order-1', payload)).toEqual(result);
    expect(post).toHaveBeenCalledWith('/admin/orders/order-1/dhl/tracking-refresh', payload, { timeout: 30000 });
  });

  it('does not retry an ambiguous booking failure or replace its idempotency key', async () => {
    const failure = new Error('timeout');
    post.mockRejectedValue(failure);
    await expect(service.createDhlBooking('order-1', { intent_id: 'intent-1', package_id: 'package-1',
      package_version: 1, seal_id: 'seal-1', idempotency_key: 'original-key' })).rejects.toBe(failure);
    expect(post).toHaveBeenCalledTimes(1);
  });
});
