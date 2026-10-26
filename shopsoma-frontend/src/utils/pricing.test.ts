import { describe, expect, it } from 'vitest';
import { resolveVariationPricing } from './pricing';

describe('resolveVariationPricing', () => {
  it('uses inherited parent sale price (base_price) instead of stale variation sale_price when inherits_sale_price is true', () => {
    // Adaeze Trousers (Blue, size 10): product base_price=49,980, compare_at_price=99,960,
    // variation has stale sale_price=83,300 with inherits_sale_price=true.
    const result = resolveVariationPricing(
      {
        price: 99960,
        sale_price: 83300,
        inherits_price: true,
        inherits_sale_price: true,
      },
      49980,
      99960
    );

    expect(result.currentPrice).toBe(49980);
    expect(result.comparePrice).toBe(99960);
  });

  it('uses inherited parent base_price instead of stale variation price when inherits_price is true and no sale exists', () => {
    const result = resolveVariationPricing(
      {
        price: 83300,
        sale_price: null,
        inherits_price: true,
        inherits_sale_price: false,
      },
      49980,
      undefined
    );

    expect(result.currentPrice).toBe(49980);
    expect(result.comparePrice).toBeUndefined();
  });

  it('uses explicit variation regular and sale prices when inheritance markers are false', () => {
    const result = resolveVariationPricing(
      {
        price: 99960,
        sale_price: 83300,
        inherits_price: false,
        inherits_sale_price: false,
      },
      49980,
      99960
    );

    expect(result.currentPrice).toBe(83300);
    expect(result.comparePrice).toBe(99960);
  });

  it('treats legacy null variation price and sale_price without markers as inherited from parent', () => {
    const result = resolveVariationPricing(
      {
        price: null,
        sale_price: null,
        inherits_price: null,
        inherits_sale_price: null,
      },
      49980,
      83300
    );

    expect(result.currentPrice).toBe(49980);
    expect(result.comparePrice).toBe(83300);
  });
});
