import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ProductDetail from './ProductDetail';

const productMocks = vi.hoisted(() => ({
  getProduct: vi.fn(),
  getProducts: vi.fn(),
}));

const wishlistMocks = vi.hoisted(() => ({
  checkInWishlist: vi.fn(),
  addToWishlist: vi.fn(),
  removeFromWishlist: vi.fn(),
}));

const addItemMock = vi.hoisted(() => vi.fn());

vi.mock('../../services/productService', () => ({
  productService: productMocks,
}));

vi.mock('../../services/wishlistService', () => ({
  wishlistService: wishlistMocks,
}));

vi.mock('../../store/cartStore', () => ({
  useCartStore: (selector: any) =>
    selector({
      addItem: addItemMock,
      error: null,
    }),
}));

vi.mock('../../store/currencyStore', () => ({
  useCurrencyStore: () => ({
    currentCurrency: 'USD',
    exchangeRates: { USD_NGN: 833.33, NGN_USD: 0.0012 },
    fetchExchangeRate: vi.fn(),
  }),
}));

vi.mock('../../components/layout/Layout', () => ({
  default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

vi.mock('../../components/modals/AddToBagModal', () => ({
  default: () => <div data-testid="add-to-bag-modal" />,
}));

vi.mock('../../components/product', () => ({
  ProductCard: () => <div data-testid="related-product" />,
}));

vi.mock('../../components/product/ProductReviews', () => ({
  ProductReviews: () => <div data-testid="product-reviews" />,
}));

describe('ProductDetail per-size pricing and default main size selection', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    productMocks.getProducts.mockResolvedValue({ products: [], total: 0 });
  });

  it('selects the main storefront size by default and updates price when a different size is selected', async () => {
    productMocks.getProduct.mockResolvedValue({
      id: 'prod-1',
      vendor_id: 'vendor-1',
      vendor_name: 'NOUVELLE GLORIA FORM STUDIO',
      title: 'Branded Jogs',
      description: 'Test trousers with per-size prices',
      base_price: 100,
      compare_at_price: 120,
      currency: 'USD',
      total_stock: 40,
      status: 'active',
      moderation_status: 'approved',
      product_type: 'single',
      made_to_order: false,
      images: [],
      variations: [],
      variants: [
        {
          id: 'var-10',
          product_id: 'prod-1',
          size: '10',
          price: 60,
          compare_at_price: 120,
          stock: 10,
          is_available: true,
          inherits_price: false,
        },
        {
          id: 'var-12',
          product_id: 'prod-1',
          size: '12',
          price: 60,
          compare_at_price: 120,
          stock: 10,
          is_available: true,
          inherits_price: false,
        },
        {
          id: 'var-14',
          product_id: 'prod-1',
          size: '14',
          price: 100,
          compare_at_price: 120,
          stock: 10,
          is_available: true,
          inherits_price: true,
        },
        {
          id: 'var-8',
          product_id: 'prod-1',
          size: '8',
          price: 60,
          compare_at_price: 120,
          stock: 10,
          is_available: true,
          inherits_price: false,
        },
      ],
    });

    render(
      <MemoryRouter initialEntries={['/products/prod-1']}>
        <Routes>
          <Route path="/products/:id" element={<ProductDetail />} />
        </Routes>
      </MemoryRouter>
    );

    // Default size should be Size: 14 (marked with inherits_price: true) and show $100.00
    expect(await screen.findByText('Size: 14')).toBeInTheDocument();
    expect(screen.getByText('$100.00')).toBeInTheDocument();

    // Open size dropdown and select Size 10 ($60.00)
    fireEvent.click(screen.getByText('Size: 14'));
    fireEvent.click(screen.getByRole('button', { name: /^10/i }));

    await waitFor(() => {
      expect(screen.getByText('Size: 10')).toBeInTheDocument();
      expect(screen.getByText('$60.00')).toBeInTheDocument();
    });

    // Clicking Add to Bag should pass the selected size's price ($60)
    fireEvent.click(screen.getByRole('button', { name: /Add to Bag/i }));
    expect(addItemMock).toHaveBeenCalledWith(
      expect.objectContaining({
        variant: expect.objectContaining({
          id: 'var-10',
          size: '10',
          price: 60,
        }),
      })
    );
  });
});
