import { beforeEach, describe, expect, it, vi } from 'vitest';

const { get, post } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));

vi.mock('../api', () => ({ default: { get, post } }));

import { shippingQuoteService } from '../shippingQuoteService';

describe('shippingQuoteService', () => {
  beforeEach(() => {
    get.mockReset();
    post.mockReset();
  });

  it('uses the protected order quote path', async () => {
    get.mockResolvedValue({ data: [] });

    await shippingQuoteService.listQuotes('order-1');

    expect(get).toHaveBeenCalledWith('/orders/order-1/shipping-quotes');
  });

  it('sends the caller idempotency key when requesting a quote', async () => {
    post.mockResolvedValue({ data: { id: 'quote-1' } });

    await shippingQuoteService.createQuote('order-1', 'quote-key');

    expect(post).toHaveBeenCalledWith('/orders/order-1/shipping-quotes', undefined, {
      headers: { 'X-Idempotency-Key': 'quote-key' },
    });
  });

  it('binds selection to the order, quote, option, and idempotency key', async () => {
    post.mockResolvedValue({ data: { id: 'quote-1' } });

    await shippingQuoteService.selectOption('order-1', 'quote-1', 'option-1', 'selection-key');

    expect(post).toHaveBeenCalledWith(
      '/orders/order-1/shipping-quotes/quote-1/options/option-1/select',
      undefined,
      { headers: { 'X-Idempotency-Key': 'selection-key' } },
    );
  });
});
