import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import ProductCard from '../ProductCard';
import type { Product } from '../../../types';

vi.mock('../../../store/currencyStore', () => ({
  useCurrencyStore: () => ({
    currentCurrency: 'USD',
    exchangeRates: { USD: 1, NGN: 1500 },
  }),
}));

vi.mock('../../../utils/pricing', () => ({
  formatPriceWithConversion: (price: number) => `$${price}`,
}));

describe('ProductCard pricing resolution', () => {
  it('displays updated base_price for single products even if variants contain stale price', () => {
    const singleProduct: Product = {
      id: 'prod-dance-dress',
      vendor_id: 'vendor-1',
      title: 'Dance dress',
      vendor_name: 'NOUVELLE GLORIA',
      base_price: 75, // Updated price
      currency: 'USD',
      status: 'active',
      product_type: 'single',
      inventory_quantity: 10,
      total_stock: 10,
      is_featured: false,
      made_to_order: false,
      views_count: 0,
      orders_count: 0,
      moderation_status: 'approved',
      images: [],
      variations: [],
      variants: [
        {
          id: 'var-1',
          product_id: 'prod-dance-dress',
          size: '12',
          color: 'Black',
          price: 85, // Stale legacy price
          stock: 5,
          is_available: true,
        },
      ],
      created_at: '2026-01-01',
      updated_at: '2026-10-02',
    };

    render(
      <MemoryRouter>
        <ProductCard product={singleProduct} />
      </MemoryRouter>
    );

    // Should display $75 (base_price), not $85
    expect(screen.getByText('$75')).toBeDefined();
    expect(screen.queryByText('$85')).toBeNull();
  });

  it('displays compare_at_price and discount for single products with sale', () => {
    const saleProduct: Product = {
      id: 'prod-sale',
      vendor_id: 'vendor-1',
      title: 'Summer Dress',
      vendor_name: 'Studio',
      base_price: 60,
      compare_at_price: 100,
      currency: 'USD',
      status: 'active',
      product_type: 'single',
      inventory_quantity: 5,
      total_stock: 5,
      is_featured: false,
      made_to_order: false,
      views_count: 0,
      orders_count: 0,
      moderation_status: 'approved',
      images: [],
      variations: [],
      variants: [],
      created_at: '2026-01-01',
      updated_at: '2026-01-01',
    };

    render(
      <MemoryRouter>
        <ProductCard product={saleProduct} />
      </MemoryRouter>
    );

    expect(screen.getByText('$60')).toBeDefined();
    expect(screen.getByText('$100')).toBeDefined();
  });
});
