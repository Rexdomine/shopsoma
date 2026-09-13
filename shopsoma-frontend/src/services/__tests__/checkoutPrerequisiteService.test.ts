import { beforeEach, describe, expect, it, vi } from 'vitest';

const { get, post, requestUse } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), requestUse: vi.fn() }));
vi.mock('axios', () => ({
  default: {
    create: vi.fn(() => ({ post, get, put: vi.fn(), delete: vi.fn(), interceptors: { request: { use: requestUse } } })),
  },
}));

vi.mock('../api', () => ({
  default: { get },
}));

import { checkoutService } from '../checkoutService';
import { orderService } from '../orderService';
import { buildPaystackWidgetConfig, paymentService } from '../paymentService';

describe('M5 checkout service capability scope', () => {
  beforeEach(() => {
    post.mockReset().mockResolvedValue({ data: {} });
    get.mockReset().mockResolvedValue({ data: {} });
  });

  it('puts capability only in headers for estimate creation and never in URL/body', async () => {
    await checkoutService.createCheckoutEstimate('order-1', 'estimate-key', 'secret-capability');

    expect(post).toHaveBeenCalledWith('/orders/order-1/checkout-estimates', undefined, {
      headers: {
        'X-Idempotency-Key': 'estimate-key',
        'X-ShopSoma-Checkout-Capability': 'secret-capability',
      },
    });
    expect(JSON.stringify(post.mock.calls[0].slice(0, 2))).not.toContain('secret-capability');
  });

  it('scopes capability and idempotency to explicit option selection', async () => {
    await checkoutService.selectCheckoutEstimateOption('order-1', 'estimate-1', 'option-1', 'selection-key', 'secret-capability');

    expect(post).toHaveBeenCalledWith(
      '/orders/order-1/checkout-estimates/estimate-1/options/option-1/select',
      undefined,
      { headers: { 'X-Idempotency-Key': 'selection-key', 'X-ShopSoma-Checkout-Capability': 'secret-capability' } },
    );
  });

  it('does not attach capability to unrelated legacy calls', async () => {
    await checkoutService.reviewOrder({ items: [], currency: 'NGN' });
    expect(post).toHaveBeenCalledWith('/orders/review', { items: [], currency: 'NGN' });
  });

  it('forwards a guest capability only as an order-read header', async () => {
    await checkoutService.getOrder('order-1', 'secret-capability');
    await orderService.getOrderTracking('order-1', 'secret-capability');

    expect(get).toHaveBeenNthCalledWith(1, '/orders/order-1', {
      headers: { 'X-ShopSoma-Checkout-Capability': 'secret-capability' },
    });
    expect(get).toHaveBeenNthCalledWith(2, '/orders/order-1/tracking', {
      headers: { 'X-ShopSoma-Checkout-Capability': 'secret-capability' },
    });
    expect(JSON.stringify(get.mock.calls.map((call) => call[0]))).not.toContain('secret-capability');
  });

  it('initializes enforced payment without client money and scopes guest capability to its header', async () => {
    await paymentService.initializePayment({
      order_id: 'order-1',
      email: 'guest@example.com',
      payment_gateway: 'paystack',
      callback_url: 'https://shop.example/payment/verify',
    }, 'secret-capability');

    expect(post).toHaveBeenCalledWith('/payments/initialize', {
      order_id: 'order-1',
      email: 'guest@example.com',
      payment_gateway: 'paystack',
      callback_url: 'https://shop.example/payment/verify',
    }, { headers: { 'X-ShopSoma-Checkout-Capability': 'secret-capability' } });
  });
});

describe('M5 provider boundary truth', () => {
  it('uses initialization amount/currency/reference without review-summary money or float rounding', () => {
    const config = buildPaystackWidgetConfig({
      status: true,
      message: 'ready',
      payment_gateway: 'paystack',
      amount_minor: 1005,
      amount: '10.05',
      currency: 'NGN',
      reference: 'server-reference',
      provider_payload: { access_code: 'server-access' },
    }, { email: 'buyer@example.com', key: 'public-key' });

    expect(config).toMatchObject({
      amount: 1005,
      currency: 'NGN',
      ref: 'server-reference',
      access_code: 'server-access',
    });
    expect(config.amount).not.toBe(99999900);
  });
});
