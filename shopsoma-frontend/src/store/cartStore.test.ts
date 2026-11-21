import { beforeEach, describe, expect, it, vi } from 'vitest';
import { CartService } from '../services/cartService';
import { useCartStore } from './cartStore';
import type { Product, ProductVariant } from '../types';

const makeProduct = (overrides: Partial<Product> = {}): Product => ({
  id: 'prod-qa-last-unit',
  vendor_id: 'vendor-kester',
  vendor_name: 'Kester Club',
  title: 'SOMA-29 QA Last Unit Item',
  description: 'Disposable QA test product',
  base_price: 4000,
  currency: 'NGN',
  total_stock: 1,
  inventory_quantity: 1,
  status: 'active',
  moderation_status: 'approved',
  product_type: 'single',
  made_to_order: false,
  is_featured: false,
  views_count: 0,
  orders_count: 0,
  images: [],
  variations: [],
  variants: [],
  created_at: '2026-11-20T00:00:00Z',
  updated_at: '2026-11-20T00:00:00Z',
  ...overrides,
});

const makeVariant = (overrides: Partial<ProductVariant> = {}): ProductVariant => ({
  id: 'default-prod-qa-last-unit',
  product_id: 'prod-qa-last-unit',
  price: 4000,
  stock: 1,
  is_available: true,
  ...overrides,
});

describe('cartStore.addItem server confirmation', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
    useCartStore.setState({
      cart: CartService.createEmptyCart(),
      isLoading: false,
      error: null,
    });
  });

  it('does not add item to cart or localStorage when server rejects with 400 out of stock', async () => {
    const product = makeProduct();
    const variant = makeVariant();
    vi.spyOn(CartService, 'addItemToServer').mockRejectedValueOnce({
      response: { status: 400, data: { detail: 'Product is out of stock' } },
    });

    const added = await useCartStore.getState().addItem({ product, variant, quantity: 1 });

    expect(added).toBe(false);
    const state = useCartStore.getState();
    expect(state.cart.items).toHaveLength(0);
    expect(state.cart.summary.itemCount).toBe(0);
    expect(state.error).toBe('Product is out of stock');
    const persisted = localStorage.getItem('shopsoma_cart');
    expect(persisted).toBeNull();
  });

  it('keeps existing cart quantity unchanged when server rejects with 409 structured insufficient_stock', async () => {
    const product = makeProduct();
    const variant = makeVariant();
    const addSpy = vi.spyOn(CartService, 'addItemToServer');
    addSpy.mockResolvedValueOnce({
      id: 'server-item-1',
      product_id: product.id,
      variant_id: null,
      quantity: 1,
      price: 4000,
      available_stock: 1,
      is_in_stock: true,
      stock_issue: null,
    });

    const firstAdded = await useCartStore.getState().addItem({ product, variant, quantity: 1 });
    expect(firstAdded).toBe(true);

    addSpy.mockRejectedValueOnce({
      response: {
        status: 409,
        data: { detail: { code: 'insufficient_stock', message: 'insufficient stock' } },
      },
    });

    const secondAdded = await useCartStore.getState().addItem({ product, variant, quantity: 1 });

    expect(secondAdded).toBe(false);
    const state = useCartStore.getState();
    expect(state.cart.items).toHaveLength(1);
    expect(state.cart.items[0].quantity).toBe(1);
    expect(state.cart.summary.itemCount).toBe(1);
    expect(state.error).toBe('insufficient stock');
    const persisted = JSON.parse(localStorage.getItem('shopsoma_cart') || '{}');
    expect(persisted.items).toHaveLength(1);
    expect(persisted.items[0].quantity).toBe(1);
  });

  it('adds item to cart, persists to localStorage, and clears error when server succeeds', async () => {
    const product = makeProduct();
    const variant = makeVariant();
    useCartStore.setState({ error: 'Previous error' });
    vi.spyOn(CartService, 'addItemToServer').mockResolvedValueOnce({
      id: 'server-item-1',
      product_id: product.id,
      variant_id: null,
      quantity: 1,
      price: 4000,
      available_stock: 1,
      is_in_stock: true,
      stock_issue: null,
    });

    const added = await useCartStore.getState().addItem({ product, variant, quantity: 1 });

    expect(added).toBe(true);
    const state = useCartStore.getState();
    expect(state.cart.items).toHaveLength(1);
    expect(state.cart.summary.itemCount).toBe(1);
    expect(state.error).toBeNull();
    const persisted = JSON.parse(localStorage.getItem('shopsoma_cart') || '{}');
    expect(persisted.items).toHaveLength(1);
    expect(persisted.items[0].product_id).toBe(product.id);
  });
});
