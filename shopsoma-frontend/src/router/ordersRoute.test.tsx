import { describe, expect, it } from 'vitest';
import { ROUTES } from '../config/constants';

describe('Orders Route Configuration', () => {
  it('defines ROUTES.ORDERS as /orders', () => {
    expect(ROUTES.ORDERS).toBe('/orders');
  });

  it('defines ROUTES.PROFILE_ORDERS as /profile/orders', () => {
    expect(ROUTES.PROFILE_ORDERS).toBe('/profile/orders');
  });
});
