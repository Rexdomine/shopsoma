import { describe, expect, it } from 'vitest';
import { gateLocationKey, shouldBypassComingSoon } from './RootLayout';

describe('gateLocationKey', () => {
  it('changes when only the query string changes', () => {
    expect(gateLocationKey('/products', '?category=dresses'))
      .not.toBe(gateLocationKey('/products', '?category=shoes'));
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
    expect(shouldBypassComingSoon('/vendor/login', null)).toBe(true);
    expect(shouldBypassComingSoon('/vendor/signup', null)).toBe(true);
    expect(shouldBypassComingSoon('/vendor/signup/business-info', null)).toBe(true);
    expect(shouldBypassComingSoon('/vendor/signup/thank-you', null)).toBe(true);
    expect(shouldBypassComingSoon('/admin/dashboard', null)).toBe(true);
    expect(shouldBypassComingSoon('/vendor/analytics', null)).toBe(true);
  });
});
