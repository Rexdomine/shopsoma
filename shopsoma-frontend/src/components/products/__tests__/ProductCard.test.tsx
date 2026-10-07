import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ProductCard from '../ProductCard';
import type { Product } from '../../../types';

const mockAddItem = vi.fn();

vi.mock('../../../store/cartStore', () => ({
  useCartStore: (selector?: (state: any) => any) => {
    const state = {
      addItem: mockAddItem,
      cart: { items: [], summary: { itemCount: 0, subtotal: 0, total: 0 } },
    };
    return selector ? selector(state) : state;
  },
}));

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
  beforeEach(() => {
    mockAddItem.mockClear();
  });

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

  it('adds item to bag when ADD TO BAG button is clicked', () => {
    const product: Product = {
      id: 'prod-shirt',
      vendor_id: 'vendor-1',
      title: 'Cotton Shirt',
      vendor_name: 'Shopsoma Studio',
      base_price: 45,
      currency: 'USD',
      status: 'active',
      product_type: 'variable',
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
          id: 'var-s-blue',
          product_id: 'prod-shirt',
          size: 'S',
          color: 'Blue',
          color_hex: '#0000ff',
          price: 45,
          stock: 5,
          is_available: true,
        },
        {
          id: 'var-m-red',
          product_id: 'prod-shirt',
          size: 'M',
          color: 'Red',
          color_hex: '#ff0000',
          price: 45,
          stock: 5,
          is_available: true,
        },
      ],
      created_at: '2026-01-01',
      updated_at: '2026-01-01',
    };

    render(
      <MemoryRouter>
        <ProductCard product={product} />
      </MemoryRouter>
    );

    const addToBagBtn = screen.getByRole('button', { name: /add to bag/i });
    expect(addToBagBtn).toBeDefined();

    fireEvent.click(addToBagBtn);

    expect(mockAddItem).toHaveBeenCalledTimes(1);
    expect(mockAddItem).toHaveBeenCalledWith({
      product,
      variant: expect.objectContaining({
        id: 'var-s-blue',
        size: 'S',
        color: 'Blue',
      }),
      quantity: 1,
    });

    expect(screen.getByRole('button', { name: /added to bag/i })).toBeDefined();
  });

  it('allows selecting size and color before adding to bag', () => {
    const product: Product = {
      id: 'prod-shirt',
      vendor_id: 'vendor-1',
      title: 'Cotton Shirt',
      vendor_name: 'Shopsoma Studio',
      base_price: 45,
      currency: 'USD',
      status: 'active',
      product_type: 'variable',
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
          id: 'var-s-blue',
          product_id: 'prod-shirt',
          size: 'S',
          color: 'Blue',
          color_hex: '#0000ff',
          price: 45,
          stock: 5,
          is_available: true,
        },
        {
          id: 'var-m-red',
          product_id: 'prod-shirt',
          size: 'M',
          color: 'Red',
          color_hex: '#ff0000',
          price: 45,
          stock: 5,
          is_available: true,
        },
      ],
      created_at: '2026-01-01',
      updated_at: '2026-01-01',
    };

    render(
      <MemoryRouter>
        <ProductCard product={product} />
      </MemoryRouter>
    );

    // Select size 'M'
    const sizeMBtn = screen.getByRole('button', { name: 'M' });
    fireEvent.click(sizeMBtn);

    // Select color 'Red'
    const colorRedBtn = screen.getByLabelText(/select color red/i);
    fireEvent.click(colorRedBtn);

    // Click Add to Bag
    const addToBagBtn = screen.getByRole('button', { name: /add to bag/i });
    fireEvent.click(addToBagBtn);

    expect(mockAddItem).toHaveBeenCalledTimes(1);
    expect(mockAddItem).toHaveBeenCalledWith({
      product,
      variant: expect.objectContaining({
        id: 'var-m-red',
        size: 'M',
        color: 'Red',
      }),
      quantity: 1,
    });
  });
});
