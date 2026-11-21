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
const cartStoreMocks = vi.hoisted(() => ({
  error: null as string | null,
}));

vi.mock('../../services/productService', () => ({
  productService: productMocks,
}));

vi.mock('../../services/wishlistService', () => ({
  wishlistService: wishlistMocks,
}));

vi.mock('../../store/cartStore', () => ({
  useCartStore: Object.assign(
    (selector: any) =>
      selector({
        addItem: addItemMock,
        error: cartStoreMocks.error,
      }),
    {
      getState: () => ({
        addItem: addItemMock,
        error: cartStoreMocks.error,
      }),
    }
  ),
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
  default: ({ open }: { open?: boolean }) => (open ? <div data-testid="add-to-bag-modal" /> : null),
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
    cartStoreMocks.error = null;
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

    // Displayed designer name links to that designer's storefront
    const designerLink = screen.getByRole('link', { name: 'NOUVELLE GLORIA FORM STUDIO' });
    expect(designerLink).toHaveAttribute('href', '/designers/vendor-1');

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

  it('navigates to the Kester Club designer storefront when clicking the displayed designer name on the product page', async () => {
    productMocks.getProduct.mockResolvedValue({
      id: 'soma-11-overshirt',
      vendor_id: 'kester-club-id',
      vendor_name: 'Kester Club',
      title: 'SOMA-11 Test Overshirt',
      description: 'Structured overshirt',
      base_price: 150,
      currency: 'USD',
      total_stock: 8,
      status: 'active',
      moderation_status: 'approved',
      product_type: 'single',
      made_to_order: false,
      images: [],
      variations: [],
      variants: [],
    });

    render(
      <MemoryRouter initialEntries={['/products/soma-11-overshirt']}>
        <Routes>
          <Route path="/products/:id" element={<ProductDetail />} />
          <Route path="/designers/:designerId" element={<div data-testid="kester-storefront">Kester Club Storefront</div>} />
        </Routes>
      </MemoryRouter>
    );

    const kesterLink = await screen.findByRole('link', { name: 'Kester Club' });
    expect(kesterLink).toHaveAttribute('href', '/designers/kester-club-id');
    fireEvent.click(kesterLink);
    expect(await screen.findByTestId('kester-storefront')).toBeInTheDocument();
  });

  it('does not open AddToBagModal and shows an alert when addItem rejects the add', async () => {
    productMocks.getProduct.mockResolvedValue({
      id: 'prod-last-unit',
      vendor_id: 'kester-club-id',
      vendor_name: 'Kester Club',
      title: 'SOMA-29 QA Last Unit Item',
      description: 'Held unit',
      base_price: 4000,
      currency: 'NGN',
      total_stock: 1,
      status: 'active',
      moderation_status: 'approved',
      product_type: 'single',
      made_to_order: false,
      images: [],
      variations: [],
      variants: [],
    });
    addItemMock.mockImplementationOnce(async () => {
      cartStoreMocks.error = 'Product is out of stock';
      return false;
    });

    render(
      <MemoryRouter initialEntries={['/products/prod-last-unit']}>
        <Routes>
          <Route path="/products/:id" element={<ProductDetail />} />
        </Routes>
      </MemoryRouter>
    );

    const addBtn = await screen.findByRole('button', { name: /Add to Bag/i });
    fireEvent.click(addBtn);

    expect(await screen.findByRole('alert')).toHaveTextContent('Product is out of stock');
    expect(screen.queryByTestId('add-to-bag-modal')).toBeNull();
  });
});
