import { describe, expect, it } from 'vitest';
import { shouldBypassComingSoon } from './RootLayout';

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

  it('keeps guests and customers behind the gate on storefront routes', () => {
    expect(shouldBypassComingSoon('/', null)).toBe(false);
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
