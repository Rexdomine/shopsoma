import { describe, expect, it } from 'vitest';
import {
  COMING_SOON_CACHE_MS,
  gateLocationKey,
  gateStateAfterRefreshFailure,
  isGateCacheFresh,
  shouldBypassComingSoon,
  shouldShowGateLoading,
} from './RootLayout';

describe('gateLocationKey', () => {
  it('changes when only the query string changes', () => {
    expect(gateLocationKey('/products', '?category=dresses'))
      .not.toBe(gateLocationKey('/products', '?category=shoes'));
  });
});

describe('isGateCacheFresh', () => {
  it('expires the public gate cache so admin changes are observed', () => {
    const resolvedAt = 1_000;
    expect(isGateCacheFresh('public', 'public', resolvedAt, resolvedAt + COMING_SOON_CACHE_MS - 1)).toBe(true);
    expect(isGateCacheFresh('public', 'public', resolvedAt, resolvedAt + COMING_SOON_CACHE_MS)).toBe(false);
  });

  it('does not reuse a cache from a different route scope', () => {
    expect(isGateCacheFresh('bypass', 'public', 1_000, 1_001)).toBe(false);
  });
});

describe('shouldShowGateLoading', () => {
  it('keeps public content mounted during same-scope cache revalidation', () => {
    expect(shouldShowGateLoading(false, false, 'open', 'public', 'public')).toBe(false);
    expect(shouldShowGateLoading(false, false, 'closed', 'public', 'public')).toBe(false);
  });

  it('blocks the initial public resolution and scope changes', () => {
    expect(shouldShowGateLoading(false, false, 'loading', null, 'public')).toBe(true);
    expect(shouldShowGateLoading(false, false, 'open', 'bypass', 'public')).toBe(true);
  });
});

describe('gateStateAfterRefreshFailure', () => {
  it('preserves a closed gate during background refresh failures', () => {
    expect(gateStateAfterRefreshFailure('closed', true)).toBe('closed');
    expect(gateStateAfterRefreshFailure('open', true)).toBe('open');
  });

  it('keeps initial failures fail-open', () => {
    expect(gateStateAfterRefreshFailure('loading', false)).toBe('open');
  });
});

describe('shouldBypassComingSoon', () => {
  it('allows admins to use the full platform', () => {
    expect(shouldBypassComingSoon('/', 'admin')).toBe(true);
    expect(shouldBypassComingSoon('/products', 'admin')).toBe(true);
  });

  it('allows vendors through their vendor namespace only', () => {
    expect(shouldBypassComingSoon('/vendor/analytics', 'vendor')).toBe(true);
    expect(shouldBypassComingSoon('/vendor/products', 'vendor')).toBe(true);
    expect(shouldBypassComingSoon('/', 'vendor')).toBe(false);
    expect(shouldBypassComingSoon('/products', 'vendor')).toBe(false);
  });

  it('preserves transactional and account-return routes', () => {
    expect(shouldBypassComingSoon('/checkout', 'customer')).toBe(true);
    expect(shouldBypassComingSoon('/order-success', 'customer')).toBe(true);
    expect(shouldBypassComingSoon('/orders/order-1', 'customer')).toBe(true);
    expect(shouldBypassComingSoon('/track/order-1', 'customer')).toBe(true);
    expect(shouldBypassComingSoon('/profile/payments', 'customer')).toBe(true);
    expect(shouldBypassComingSoon('/products', 'customer')).toBe(false);
  });

  it('preserves login and protected route entry points', () => {
    expect(shouldBypassComingSoon('/login', null)).toBe(true);
    expect(shouldBypassComingSoon('/register', null)).toBe(true);
    expect(shouldBypassComingSoon('/vendor/login', null)).toBe(true);
    expect(shouldBypassComingSoon('/vendor/signup', null)).toBe(true);
    expect(shouldBypassComingSoon('/vendor/signup/business-info', null)).toBe(true);
    expect(shouldBypassComingSoon('/vendor/signup/thank-you', null)).toBe(true);
    expect(shouldBypassComingSoon('/admin/dashboard', null)).toBe(true);
    expect(shouldBypassComingSoon('/vendor/analytics', null)).toBe(true);
  });
});
