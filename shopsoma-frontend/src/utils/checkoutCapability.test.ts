import { beforeEach, describe, expect, it } from 'vitest';

import {
  clearStoredCheckoutCapability,
  loadCheckoutCapability,
  saveCheckoutCapability,
} from './checkoutCapability';

describe('checkoutCapability session bridge', () => {
  beforeEach(() => sessionStorage.clear());

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
});
