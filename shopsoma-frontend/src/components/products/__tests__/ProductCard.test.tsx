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

  it('does not show Added to bag when addItem resolves to false', async () => {
    mockAddItem.mockResolvedValueOnce(false);
    const product: Product = {
      id: 'prod-last-unit',
      vendor_id: 'vendor-1',
      title: 'Last Unit Dress',
      vendor_name: 'Kester Club',
      base_price: 4000,
      currency: 'NGN',
      status: 'active',
      product_type: 'single',
      inventory_quantity: 1,
      total_stock: 1,
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
        <ProductCard product={product} />
      </MemoryRouter>
    );

    const addToBagBtn = screen.getByRole('button', { name: /add to bag/i });
    fireEvent.click(addToBagBtn);

    await Promise.resolve();
    expect(mockAddItem).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('button', { name: /added to bag/i })).toBeNull();
    expect(screen.getByRole('button', { name: /add to bag/i })).toBeInTheDocument();
  });

  it('disables and greys out button with OUT OF STOCK for single product with zero stock', () => {
    const product: Product = {
      id: 'prod-zero-stock',
      vendor_id: 'vendor-1',
      title: 'SOMA-29 QA Last Unit Item',
      vendor_name: 'Kester Club',
      base_price: 4000,
      currency: 'NGN',
      status: 'active',
      product_type: 'single',
      inventory_quantity: 0,
      total_stock: 0,
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
        <ProductCard product={product} />
      </MemoryRouter>
    );

    const button = screen.getByRole('button', { name: /out of stock/i });
    expect(button).toBeDisabled();
    expect(button.className).toContain('bg-gray-300');
    expect(button.className).toContain('cursor-not-allowed');

    fireEvent.click(button);
    expect(mockAddItem).not.toHaveBeenCalled();
  });

  it('updates OUT OF STOCK state dynamically when switching between out-of-stock and in-stock variants', () => {
    const product: Product = {
      id: 'prod-mixed-stock',
      vendor_id: 'vendor-1',
      title: 'Variable Dress',
      vendor_name: 'Kester Club',
      base_price: 15000,
      currency: 'NGN',
      status: 'active',
      product_type: 'variable',
      inventory_quantity: 3,
      total_stock: 3,
      is_featured: false,
      made_to_order: false,
      views_count: 0,
      orders_count: 0,
      moderation_status: 'approved',
      images: [],
      variations: [],
      variants: [
        {
          id: 'var-s',
          product_id: 'prod-mixed-stock',
          size: 'S',
          price: 15000,
          stock: 0,
          is_available: false,
        },
        {
          id: 'var-m',
          product_id: 'prod-mixed-stock',
          size: 'M',
          price: 15000,
          stock: 3,
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

    expect(screen.getByRole('button', { name: /out of stock/i })).toBeDisabled();

    fireEvent.click(screen.getByRole('button', { name: 'M' }));
    const addBtn = screen.getByRole('button', { name: /add to bag/i });
    expect(addBtn).toBeEnabled();
  });

  it('keeps ADD TO BAG enabled for made-to-order products even when total_stock is 0', () => {
    const product: Product = {
      id: 'prod-mto',
      vendor_id: 'vendor-1',
      title: 'Bespoke Gown',
      vendor_name: 'Kester Club',
      base_price: 50000,
      currency: 'NGN',
      status: 'active',
      product_type: 'single',
      inventory_quantity: 0,
      total_stock: 0,
      is_featured: false,
      made_to_order: true,
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
        <ProductCard product={product} />
      </MemoryRouter>
    );

    const addBtn = screen.getByRole('button', { name: /add to bag/i });
    expect(addBtn).toBeEnabled();
  });
});
