import { beforeEach, describe, expect, it } from 'vitest';

import {
  clearStoredCheckoutCapability,
  loadCheckoutCapability,
  saveCheckoutCapability,
} from './checkoutCapability';

describe('checkoutCapability session bridge', () => {
  beforeEach(() => {
    const values = new Map<string, string>();
    const storage = {
      clear: () => values.clear(),
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value),
      removeItem: (key: string) => values.delete(key),
    };
    Object.defineProperty(globalThis, 'sessionStorage', { configurable: true, value: storage });
    Object.defineProperty(window, 'sessionStorage', { configurable: true, value: storage });
    Object.defineProperty(window, 'localStorage', { configurable: true, value: storage });
  });

  it('scopes a guest checkout capability to one order within session storage', () => {
    saveCheckoutCapability('order-1', 'secret-capability');
    saveCheckoutCapability('order-2', 'other-capability');

    expect(loadCheckoutCapability('order-1')).toBe('secret-capability');
    expect(loadCheckoutCapability('order-2')).toBe('other-capability');
    expect(loadCheckoutCapability('missing-order')).toBeUndefined();
  });

  it('clears only the requested order capability', () => {
    saveCheckoutCapability('order-1', 'secret-capability');
    saveCheckoutCapability('order-2', 'other-capability');

    clearStoredCheckoutCapability('order-1');

    expect(loadCheckoutCapability('order-1')).toBeUndefined();
    expect(loadCheckoutCapability('order-2')).toBe('other-capability');
  });

  it('migrates a capability saved under the legacy unnormalized key', () => {
    sessionStorage.setItem('shopsoma_checkout_capability:shp-legacy', 'legacy-token');

    expect(loadCheckoutCapability('shp-legacy')).toBe('legacy-token');
    clearStoredCheckoutCapability('shp-legacy');
    expect(loadCheckoutCapability('SHP-LEGACY')).toBeUndefined();
  });

  it('uses one case-insensitive key for save, load, and clear', () => {
    saveCheckoutCapability(' shp-2026-ab12 ', 'secret-token');
    expect(loadCheckoutCapability('SHP-2026-AB12')).toBe('secret-token');

    clearStoredCheckoutCapability('ShP-2026-Ab12');
    expect(loadCheckoutCapability('shp-2026-ab12')).toBeUndefined();
  });
});
