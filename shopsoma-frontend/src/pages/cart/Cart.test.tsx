import type { ReactNode } from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  navigate: vi.fn(),
  getProducts: vi.fn(),
  validateCartItemsWithServer: vi.fn(),
  getLocalCartValidationIssues: vi.fn(),
  updateQuantity: vi.fn(),
  updateVariant: vi.fn(),
  removeItem: vi.fn(),
  toggleFavorite: vi.fn(),
  cartState: {
    cart: {
      items: [
        {
          id: 'product-1_variant-1',
          product_id: 'product-1',
          quantity: 1,
          price: 50000,
          subtotal: 50000,
          product: {
            id: 'product-1',
            title: 'Kester Club Tee',
            currency: 'NGN',
            base_price: 50000,
            total_stock: 0,
            made_to_order: false,
            vendor_name: 'Kester Club',
            images: [],
          },
          variant: {
            id: 'variant-1',
            product_id: 'product-1',
            size: 'M',
            color: 'Black',
            price: 50000,
            stock: 0,
            is_available: false,
          },
        },
      ],
      summary: { subtotal: 50000, shipping: 0, tax: 0, discount: 0, total: 50000, itemCount: 1 },
      lastUpdated: '2026-01-01T00:00:00Z',
    },
  },
}));

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mocks.navigate,
  };
});

vi.mock('../../components/layout/Layout', () => ({
  default: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}));

vi.mock('../../components/products/ProductCard', () => ({
  default: () => <div />,
}));

vi.mock('../../components/modals/EditVariantModal', () => ({
  default: () => null,
}));

vi.mock('../../hooks/useWishlistActions', () => ({
  useWishlistActions: () => ({
    favorites: new Set<string>(),
    toggleFavorite: mocks.toggleFavorite,
  }),
}));

vi.mock('../../store/preferenceStore', () => ({
  usePreferenceStore: (selector: (s: { currency: 'NGN' }) => unknown) => selector({ currency: 'NGN' }),
}));

vi.mock('../../store/currencyStore', () => ({
  useCurrencyStore: (selector: (s: { exchangeRates: Record<string, number> }) => unknown) =>
    selector({ exchangeRates: { NGN: 1, USD: 0.000625 } }),
}));

vi.mock('../../store/cartStore', () => ({
  useCartStore: (
    selector: (s: typeof mocks.cartState & {
      updateQuantity: typeof mocks.updateQuantity;
      updateVariant: typeof mocks.updateVariant;
      removeItem: typeof mocks.removeItem;
    }) => unknown,
  ) =>
    selector({
      ...mocks.cartState,
      updateQuantity: mocks.updateQuantity,
      updateVariant: mocks.updateVariant,
      removeItem: mocks.removeItem,
    }),
}));

vi.mock('../../services/productService', () => ({
  productService: {
    getProducts: mocks.getProducts,
  },
}));

vi.mock('../../services/cartService', () => ({
  CartService: {
    validateCartItemsWithServer: mocks.validateCartItemsWithServer,
    getLocalCartValidationIssues: mocks.getLocalCartValidationIssues,
  },
}));

import Cart from './Cart';

describe('Cart stock validation guardrails', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mocks.getProducts.mockResolvedValue({ products: [] });
    mocks.getLocalCartValidationIssues.mockReturnValue([]);
  });

  it('blocks Proceed to Checkout and shows an out-of-stock message when a cart item is out of stock', async () => {
    mocks.validateCartItemsWithServer.mockResolvedValue({
      is_valid: false,
      items: [
        {
          product_id: 'product-1',
          variant_id: 'variant-1',
          product_title: 'Kester Club Tee',
          requested_quantity: 1,
          available_stock: 0,
          is_in_stock: false,
          made_to_order: false,
          status: 'out_of_stock',
          message: 'Kester Club Tee is out of stock.',
        },
      ],
      errors: ['Kester Club Tee is out of stock.'],
    });

    render(
      <MemoryRouter>
        <Cart />
      </MemoryRouter>,
    );

    expect(await screen.findAllByText('Kester Club Tee is out of stock.')).toHaveLength(2);
    const checkoutButton = screen.getByRole('button', { name: 'Proceed to Checkout' });
    expect(checkoutButton).toBeDisabled();
    fireEvent.click(checkoutButton);
    expect(mocks.navigate).not.toHaveBeenCalled();
  });

  it('allows Proceed to Checkout when all cart items are in stock', async () => {
    mocks.validateCartItemsWithServer.mockResolvedValue({
      is_valid: true,
      items: [
        {
          product_id: 'product-1',
          variant_id: 'variant-1',
          product_title: 'Kester Club Tee',
          requested_quantity: 1,
          available_stock: 37,
          is_in_stock: true,
          made_to_order: false,
          status: 'ok',
          message: null,
        },
      ],
      errors: [],
    });

    render(
      <MemoryRouter>
        <Cart />
      </MemoryRouter>,
    );

    const checkoutButton = await screen.findByRole('button', { name: 'Proceed to Checkout' });
    await waitFor(() => expect(checkoutButton).toBeEnabled());
    fireEvent.click(checkoutButton);
    await waitFor(() => expect(mocks.navigate).toHaveBeenCalledWith('/checkout'));
  });
});
