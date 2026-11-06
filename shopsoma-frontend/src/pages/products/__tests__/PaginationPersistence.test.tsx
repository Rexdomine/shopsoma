import type { ReactNode } from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import ProductCard from '../../../components/products/ProductCard';
import ProductDetail from '../ProductDetail';
import ProductList from '../ProductList';
import WomenStorefront from '../WomenStorefront';
import AdminProducts from '../../admin/AdminProducts';
import AdminProductDetail from '../../admin/AdminProductDetail';
import type { Product } from '../../../types';

const { getProductsMock, getSubcategoriesMock } = vi.hoisted(() => ({
  getProductsMock: vi.fn(),
  getSubcategoriesMock: vi.fn(),
}));

const mocks = vi.hoisted(() => ({
  get: vi.fn(),
  put: vi.fn(),
  error: vi.fn(),
  success: vi.fn(),
  warning: vi.fn(),
  hideToast: vi.fn(),
  setCurrency: vi.fn(),
  fetchExchangeRate: vi.fn(),
}));

vi.mock('../../../services/productService', () => ({
  productService: {
    getProducts: getProductsMock,
    getProduct: vi.fn(),
  },
}));

vi.mock('../../../services/categoryService', () => ({
  categoryService: {
    getSubcategories: getSubcategoriesMock,
    getPrimaryCategories: vi.fn().mockResolvedValue([]),
    getAllCategories: vi.fn().mockResolvedValue([]),
  },
}));

vi.mock('../../../services/featuredStorefrontService', () => ({
  getFeaturedStorefrontVendors: vi.fn().mockResolvedValue([]),
}));

vi.mock('../../../services/settingsService', () => ({
  getFeaturedRotationSettings: vi.fn().mockResolvedValue({ rotation_minutes: 10 }),
}));

vi.mock('../../../hooks/useWishlistActions', () => ({
  useWishlistActions: () => ({ favorites: new Set(), toggleFavorite: vi.fn(), loadingIds: new Set() }),
}));

vi.mock('../../../store/preferenceStore', () => ({
  usePreferenceStore: (selector: (state: { interest: null }) => unknown) => selector({ interest: null }),
}));

vi.mock('../../../store/currencyStore', () => ({
  useCurrencyStore: () => ({
    currentCurrency: 'NGN',
    exchangeRates: {},
    setCurrency: mocks.setCurrency,
    fetchExchangeRate: mocks.fetchExchangeRate,
  }),
}));

vi.mock('../../../services/api', () => ({
  default: { get: mocks.get, put: mocks.put },
}));

vi.mock('../../../hooks/useToast', () => ({
  useToast: () => ({
    toasts: [],
    error: mocks.error,
    success: mocks.success,
    warning: mocks.warning,
    hideToast: mocks.hideToast,
  }),
}));

vi.mock('../../../components/common/CurrencySwitcher', () => ({ default: () => null }));
vi.mock('../../../components/admin/AdminSidebar', () => ({ default: () => null }));
vi.mock('../../../components/layout/Layout', () => ({
  default: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}));

function LocationObserver() {
  const location = useLocation();
  return (
    <div data-testid="location-observer">
      <span data-testid="location-pathname">{location.pathname}</span>
      <span data-testid="location-search">{location.search}</span>
      <span data-testid="location-state">{JSON.stringify(location.state)}</span>
    </div>
  );
}

const sampleProduct: Product = {
  id: 'prod-100',
  vendor_id: 'vendor-1',
  vendor_name: 'Atelier Soma',
  title: 'Tailored Wool Coat',
  description: 'Classic outerwear',
  base_price: 45000,
  compare_at_price: undefined,
  currency: 'NGN',
  category_name: 'Men',
  inventory_quantity: 10,
  total_stock: 10,
  made_to_order: false,
  status: 'active',
  is_featured: false,
  product_type: 'single',
  moderation_status: 'approved',
  views_count: 0,
  orders_count: 0,
  created_at: '2026-10-01T00:00:00Z',
  updated_at: '2026-10-01T00:00:00Z',
  images: [],
  variants: [],
};

describe('Pagination Persistence on Back Navigation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    localStorage.clear();
    getProductsMock.mockReset();
    getSubcategoriesMock.mockReset();
  });

  afterEach(() => {
    sessionStorage.clear();
    localStorage.clear();
  });

  describe('ProductCard & ProductDetail', () => {
    it('ProductCard passes current pathname and search query in location state', async () => {
      render(
        <MemoryRouter initialEntries={['/products?page=3&sort=newest']}>
          <LocationObserver />
          <Routes>
            <Route path="/products" element={<ProductCard product={sampleProduct} />} />
            <Route path="/products/:id" element={<div>Product Detail Target</div>} />
          </Routes>
        </MemoryRouter>
      );

      const link = screen.getByRole('link', { name: new RegExp(sampleProduct.title, 'i') });
      expect(link).toHaveAttribute('href', `/products/${sampleProduct.id}`);

      fireEvent.click(link);

      await waitFor(() => {
        expect(screen.getByTestId('location-pathname')).toHaveTextContent(`/products/${sampleProduct.id}`);
        expect(screen.getByTestId('location-state')).toHaveTextContent('/products?page=3&sort=newest');
      });
    });

    it('ProductDetail Back button returns to the originating page URL stored in location.state.from', async () => {
      const { productService } = await import('../../../services/productService');
      vi.mocked(productService.getProduct).mockResolvedValue(sampleProduct);

      render(
        <MemoryRouter
          initialEntries={[
            {
              pathname: `/products/${sampleProduct.id}`,
              state: { from: '/products?page=3' },
            },
          ]}
        >
          <LocationObserver />
          <Routes>
            <Route path="/products/:id" element={<ProductDetail />} />
            <Route path="/products" element={<div>Products List Page</div>} />
          </Routes>
        </MemoryRouter>
      );

      await waitFor(() => {
        expect(screen.getByText('Back')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('Back'));

      await waitFor(() => {
        expect(screen.getByTestId('location-pathname')).toHaveTextContent('/products');
        expect(screen.getByTestId('location-search')).toHaveTextContent('?page=3');
      });
    });
  });

  describe('ProductList page preservation', () => {
    it('preserves page=3 in URL when initialParams resolves asynchronously', async () => {
      // 36 products = 3 pages of 12
      const products = Array.from({ length: 36 }, (_, i) => ({
        ...sampleProduct,
        id: `p-${i + 1}`,
        title: `Product ${i + 1}`,
      }));

      getProductsMock.mockResolvedValue({
        products,
        total: 36,
        total_pages: 1,
      });

      const { rerender } = render(
        <MemoryRouter initialEntries={['/men?page=3']}>
          <LocationObserver />
          <ProductList presetCategory="Men" initialParams={{ category_id: 'cat-men' }} />
        </MemoryRouter>
      );

      await waitFor(() => {
        expect(screen.getByTestId('location-search')).toHaveTextContent('?page=3');
      });

      // Simulate MenStorefront resolving the database category UUID
      rerender(
        <MemoryRouter initialEntries={['/men?page=3']}>
          <LocationObserver />
          <ProductList presetCategory="Men" initialParams={{ category_id: 'real-db-uuid-men' }} />
        </MemoryRouter>
      );

      // Page 3 must NOT be wiped out to page 1
      await waitFor(() => {
        expect(screen.getByTestId('location-search')).toHaveTextContent('?page=3');
      });
    });

    it("returns to Women's Dresses page 2 and restores scroll position when tapping in-page Back button", async () => {
      const { productService } = await import('../../../services/productService');
      const { categoryService } = await import('../../../services/categoryService');

      const dressProducts: Product[] = Array.from({ length: 18 }, (_, i) => ({
        ...sampleProduct,
        id: i === 12 ? 'prod-agbada' : `dress-${i + 1}`,
        title: i === 12 ? 'PETTRE TAYLOR Checkered Agbada' : `Luxury Dress ${i + 1}`,
        category_name: "Women's Dresses",
        category_parent_name: 'Women',
        categories: ['Women', "Women's Dresses"],
      }));

      vi.mocked(categoryService.getPrimaryCategories).mockResolvedValue([
        {
          id: 'db-women-uuid',
          name: 'Women',
          slug: 'women',
          display_order: 1,
          is_active: true,
          created_at: '2026-10-01T00:00:00Z',
          updated_at: '2026-10-01T00:00:00Z',
        },
      ]);

      getSubcategoriesMock.mockImplementation(async (parentId: string) => {
        if (parentId === 'db-women-uuid') {
          return [
            {
              id: 'db-women-dresses-uuid',
              name: "Women's Dresses",
              slug: 'women-dresses',
              parent_id: 'db-women-uuid',
              display_order: 1,
              is_active: true,
              created_at: '2026-10-01T00:00:00Z',
              updated_at: '2026-10-01T00:00:00Z',
            },
          ];
        }
        return [];
      });

      getProductsMock.mockResolvedValue({
        products: dressProducts,
        total: dressProducts.length,
        total_pages: 1,
      });

      vi.mocked(productService.getProduct).mockResolvedValue(dressProducts[12]);

      const scrollToSpy = vi.spyOn(window, 'scrollTo').mockImplementation(() => {});
      Object.defineProperty(window, 'scrollY', { value: 480, writable: true, configurable: true });

      render(
        <MemoryRouter initialEntries={['/women']}>
          <LocationObserver />
          <Routes>
            <Route path="/women" element={<WomenStorefront />} />
            <Route path="/products/:id" element={<ProductDetail />} />
          </Routes>
        </MemoryRouter>
      );

      // 1. Wait for initial Women listing to render
      await waitFor(() => {
        expect(screen.getAllByText('Luxury Dress 1').length).toBeGreaterThan(0);
      });

      // 2. Select Women's Dresses
      const dressesTab = screen.getByRole('button', { name: "Women's Dresses" });
      fireEvent.click(dressesTab);

      await waitFor(() => {
        expect(screen.getByTestId('location-search')).toHaveTextContent('category=Women%27s+Dresses');
      });

      // 3. Go to listing page 2
      const page2Button = await screen.findByRole('button', { name: '2' });
      fireEvent.click(page2Button);

      await waitFor(() => {
        expect(screen.getByTestId('location-search')).toHaveTextContent('category=Women%27s+Dresses');
        expect(screen.getByTestId('location-search')).toHaveTextContent('page=2');
        expect(screen.getAllByText('PETTRE TAYLOR Checkered Agbada').length).toBeGreaterThan(0);
      });

      // 4. Open PETTRE TAYLOR Checkered Agbada
      const productLinks = screen.getAllByRole('link', { name: /PETTRE TAYLOR Checkered Agbada/i });
      fireEvent.click(productLinks[0]);

      await waitFor(() => {
        expect(screen.getByTestId('location-pathname')).toHaveTextContent('/products/prod-agbada');
      });

      // 5. Tap the product page's in-page <- BACK control
      const backButton = await screen.findByRole('button', { name: /back/i });
      scrollToSpy.mockClear();
      fireEvent.click(backButton);

      // 6. Verify it returns to Women's Dresses on page 2 (not All Items) and restores scroll
      await waitFor(() => {
        expect(screen.getByTestId('location-pathname')).toHaveTextContent('/women');
        expect(screen.getByTestId('location-search')).toHaveTextContent('category=Women%27s+Dresses');
        expect(screen.getByTestId('location-search')).toHaveTextContent('page=2');
        expect(screen.getAllByText('PETTRE TAYLOR Checkered Agbada').length).toBeGreaterThan(0);
      });

      const returnedDressesTab = screen.getByRole('button', { name: "Women's Dresses" });
      const allItemsTab = screen.getByRole('button', { name: /All Items/i });
      expect(returnedDressesTab.className).toContain('border-primary');
      expect(allItemsTab.className).toContain('border-transparent');
      expect(scrollToSpy).toHaveBeenCalledWith({ top: 480, behavior: 'auto' });

      scrollToSpy.mockRestore();
    });
  });

  describe('AdminProducts & AdminProductDetail pagination', () => {
    it('AdminProducts reads page number from URL search parameters and passes from state on view', async () => {
      mocks.get.mockImplementation(async (url: string) => {
        if (url.startsWith('/admin/products?')) {
          return {
            data: {
              items: [{ ...sampleProduct, sku: 'SKU-PAGE-3', vendor: { id: 'vendor-1', business_name: 'Test Vendor' } }],
              total: 50,
              page: 3,
              page_size: 20,
              total_pages: 3,
            },
          };
        }
        if (url === '/admin/products/prod-100') {
          return { data: sampleProduct };
        }
        throw new Error('Not found');
      });

      render(
        <MemoryRouter initialEntries={['/admin/products?page=3']}>
          <LocationObserver />
          <Routes>
            <Route path="/admin/products" element={<AdminProducts />} />
            <Route path="/admin/products/:id" element={<AdminProductDetail />} />
          </Routes>
        </MemoryRouter>
      );

      await waitFor(() => {
        expect(screen.getByText('Showing page 3 of 3 (50 total products)')).toBeInTheDocument();
      });

      // Click "View Details" (Eye icon button)
      const viewButton = screen.getByTitle('View Details');
      fireEvent.click(viewButton);

      await waitFor(() => {
        expect(screen.getByTestId('location-pathname')).toHaveTextContent('/admin/products/prod-100');
        expect(screen.getByTestId('location-state')).toHaveTextContent('/admin/products?page=3');
      });

      // Click "Back to Products"
      const backButton = screen.getByRole('button', { name: /back to products/i });
      fireEvent.click(backButton);

      await waitFor(() => {
        expect(screen.getByTestId('location-pathname')).toHaveTextContent('/admin/products');
        expect(screen.getByTestId('location-search')).toHaveTextContent('?page=3');
      });
    });
  });
});
