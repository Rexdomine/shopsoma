import { describe, expect, it } from 'vitest';
import { ROUTES } from '../config/constants';
import { router } from './index';

describe('Orders Route Configuration', () => {
  it('defines ROUTES.ORDERS as /orders', () => {
    expect(ROUTES.ORDERS).toBe('/orders');
  });

  it('defines ROUTES.PROFILE_ORDERS as /profile/orders', () => {
    expect(ROUTES.PROFILE_ORDERS).toBe('/profile/orders');
  });

  it('configures live map tracking routes for both /track/:orderId/map and /orders/:orderId/map', () => {
    const rootRoutes = router.routes[0]?.children || [];
    const paths = rootRoutes.map((r: any) => r.path);
    expect(paths).toContain(ROUTES.ORDER_MAP_TRACKING);
    expect(paths).toContain('/orders/:orderId/map');
    expect(paths).toContain('/orders/:orderId/tracking');
  });
});
