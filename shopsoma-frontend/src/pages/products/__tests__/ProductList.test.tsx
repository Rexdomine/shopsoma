import type { ReactNode } from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ProductList from '../ProductList';

const { getProductsMock, getSubcategoriesMock } = vi.hoisted(() => ({
  getProductsMock: vi.fn(),
  getSubcategoriesMock: vi.fn(),
}));
const { getFeaturedStorefrontVendorsMock, getFeaturedRotationSettingsMock } = vi.hoisted(() => ({
  getFeaturedStorefrontVendorsMock: vi.fn(),
  getFeaturedRotationSettingsMock: vi.fn(),
}));

vi.mock('../../../services/productService', () => ({
  productService: { getProducts: getProductsMock },
}));
vi.mock('../../../services/categoryService', () => ({
  categoryService: { getSubcategories: getSubcategoriesMock },
}));
vi.mock('../../../services/featuredStorefrontService', () => ({
  getFeaturedStorefrontVendors: getFeaturedStorefrontVendorsMock,
}));
vi.mock('../../../services/settingsService', () => ({
  getFeaturedRotationSettings: getFeaturedRotationSettingsMock,
}));
vi.mock('../../../hooks/useWishlistActions', () => ({
  useWishlistActions: () => ({ favorites: new Set(), toggleFavorite: vi.fn(), loadingIds: new Set() }),
}));
vi.mock('../../../store/preferenceStore', () => ({
  usePreferenceStore: (selector: (state: { interest: null }) => unknown) => selector({ interest: null }),
}));
vi.mock('../../../components/layout/Layout', () => ({
  default: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}));
vi.mock('../../../components/common/Loading', () => ({
  default: ({ message }: { message?: string }) => <div>{message}</div>,
}));
vi.mock('../../../components/products/ProductCard', () => ({
  default: ({ product }: { product: { id: string } }) => <div data-testid={`product-${product.id}`}>Product</div>,
}));
vi.mock('../../../components/products/VendorShowcaseCard', () => ({
  default: ({ imageUrl }: { imageUrl: string }) => <div data-testid="vendor-image">{imageUrl}</div>,
}));

describe('ProductList', () => {
  beforeEach(() => {
    getProductsMock.mockReset();
    getSubcategoriesMock.mockReset();
    getFeaturedStorefrontVendorsMock.mockReset();
    getFeaturedRotationSettingsMock.mockReset();
    getProductsMock.mockResolvedValue({ products: [] });
    getSubcategoriesMock.mockResolvedValue([]);
    getFeaturedStorefrontVendorsMock.mockResolvedValue([]);
    getFeaturedRotationSettingsMock.mockResolvedValue({ rotation_minutes: 10 });
    window.sessionStorage.clear();
  });

  it('renders the first category page before background pages finish loading', async () => {
    let resolveSecondPage: ((value: { products: never[] }) => void) | undefined;
    const secondPage = new Promise<{ products: never[] }>((resolve) => {
      resolveSecondPage = resolve;
    });
    getProductsMock
      .mockResolvedValueOnce({ products: [{ id: 'first-page-product', category_name: 'Men' }], total_pages: 2 })
      .mockReturnValueOnce(secondPage);

    render(<MemoryRouter><ProductList initialParams={{ category_id: 'men-id' }} /></MemoryRouter>);

    await waitFor(() => expect(screen.getAllByTestId('product-first-page-product')).not.toHaveLength(0));
    expect(screen.queryByText('Preparing the catalog...')).not.toBeInTheDocument();
    resolveSecondPage?.({ products: [] });
  });

  it('ignores stale category enrichment after initialParams change', async () => {
    let resolveOldSecondPage: ((value: { products: never[] }) => void) | undefined;
    const oldSecondPage = new Promise<{ products: never[] }>((resolve) => {
      resolveOldSecondPage = resolve;
    });
    getProductsMock
      .mockResolvedValueOnce({ products: [{ id: 'old-category-first-page', category_name: 'Men' }], total_pages: 2 })
      .mockReturnValueOnce(oldSecondPage)
      .mockResolvedValueOnce({ products: [{ id: 'new-category-product', category_name: 'Women' }], total_pages: 1 });

    const { rerender } = render(
      <MemoryRouter><ProductList initialParams={{ category_id: 'old-category-id' }} /></MemoryRouter>,
    );
    await waitFor(() => expect(screen.getAllByTestId('product-old-category-first-page')).not.toHaveLength(0));

    rerender(<MemoryRouter><ProductList initialParams={{ category_id: 'new-category-id' }} /></MemoryRouter>);
    await waitFor(() => expect(screen.getAllByTestId('product-new-category-product')).not.toHaveLength(0));
    resolveOldSecondPage?.({ products: [] });
    await waitFor(() => expect(screen.queryByTestId('product-old-category-first-page')).not.toBeInTheDocument());
  });

  it('does not render cached products until the API revalidates them', async () => {
    let resolveProducts: ((value: { products: { id: string; category_name: string }[] }) => void) | undefined;
    const revalidation = new Promise<{ products: { id: string; category_name: string }[] }>((resolve) => {
      resolveProducts = resolve;
    });
    window.sessionStorage.setItem(
      'shopsoma_products_all',
      JSON.stringify({ products: [{ id: 'stale-product', category_name: 'Men' }], timestamp: Date.now() }),
    );
    getProductsMock.mockReturnValueOnce(revalidation);

    render(<MemoryRouter><ProductList /></MemoryRouter>);

    expect(screen.queryByTestId('product-stale-product')).not.toBeInTheDocument();
    resolveProducts?.({ products: [{ id: 'fresh-product', category_name: 'Men' }] });
    await waitFor(() => expect(screen.getAllByTestId('product-fresh-product')).not.toHaveLength(0));
  });

  it('fails closed when cached products cannot be revalidated', async () => {
    window.sessionStorage.setItem(
      'shopsoma_products_all',
      JSON.stringify({ products: [{ id: 'unverified-product', category_name: 'Men' }], timestamp: Date.now() }),
    );
    getProductsMock.mockRejectedValueOnce(new Error('temporary API failure'));
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined);

    render(<MemoryRouter><ProductList /></MemoryRouter>);

    await waitFor(() => expect(screen.getByText('We could not load the current collection. Please refresh.')).toBeInTheDocument());
    expect(screen.queryByTestId('product-unverified-product')).not.toBeInTheDocument();
    errorSpy.mockRestore();
  });

  it('keeps API products visible when session storage caching fails', async () => {
    getProductsMock.mockResolvedValue({
      products: [{ id: 'uncached-product', category_name: 'Men' }],
    });
    const setItemSpy = vi.spyOn(window.sessionStorage, 'setItem').mockImplementation(() => {
      throw new DOMException('quota exceeded', 'QuotaExceededError');
    });

    render(<MemoryRouter><ProductList /></MemoryRouter>);

    await waitFor(() => expect(screen.getAllByTestId('product-uncached-product')).not.toHaveLength(0));
    expect(screen.queryByText('We could not load the current collection. Please refresh.')).not.toBeInTheDocument();
    setItemSpy.mockRestore();
  });

  it('refetches when initialParams change', async () => {
    const { rerender } = render(<MemoryRouter><ProductList /></MemoryRouter>);
    await waitFor(() => expect(getProductsMock).toHaveBeenCalledTimes(1));
    rerender(<MemoryRouter><ProductList initialParams={{ category_id: 'men-id' }} /></MemoryRouter>);
    await waitFor(() => expect(getProductsMock).toHaveBeenCalledTimes(2));
    expect(getProductsMock.mock.calls[1][0]).toEqual(expect.objectContaining({ category_id: 'men-id' }));
  });

  it('uses server-curated Shop Edit tabs and resets All Items to the parent request', async () => {
    getProductsMock.mockResolvedValue({
      products: [{ id: 'party-product', category_name: 'Dresses' }],
    });
    const categoryNav = [
      { id: 'casual-id', name: 'Casual', slug: 'casual', is_active: true, display_order: 1, created_at: '', updated_at: '' },
      { id: 'evening-id', name: 'Evening', slug: 'evening', is_active: true, display_order: 2, created_at: '', updated_at: '' },
      { id: 'party-id', name: 'Party', slug: 'party', is_active: true, display_order: 3, created_at: '', updated_at: '' },
      { id: 'workwear-id', name: 'Workwear', slug: 'workwear', is_active: true, display_order: 4, created_at: '', updated_at: '' },
    ];

    render(
      <MemoryRouter>
        <ProductList
          presetCategory="Shop Edits"
          initialParams={{ category_id: 'shop-edits-id' }}
          categoryNav={categoryNav}
          categoryNavAsTabs
        />
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getAllByTestId('product-party-product')).not.toHaveLength(0));
    expect(screen.getByRole('button', { name: 'Casual' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Evening' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Party' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Workwear' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Collections' })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Party' }));
    await waitFor(() => expect(getProductsMock).toHaveBeenLastCalledWith(expect.objectContaining({ category_id: 'party-id' })));

    fireEvent.click(screen.getByRole('button', { name: /All Items/ }));
    await waitFor(() => expect(getProductsMock).toHaveBeenLastCalledWith(expect.objectContaining({ category_id: 'shop-edits-id' })));

    fireEvent.click(screen.getByRole('button', { name: 'REFINE' }));
    fireEvent.click(screen.getByRole('button', { name: 'Clear All' }));
    await waitFor(() => expect(getProductsMock).toHaveBeenLastCalledWith(expect.objectContaining({ category_id: 'shop-edits-id' })));
  });

  it('keeps every desktop product visible when no featured vendor is available', async () => {
    getProductsMock.mockResolvedValue({
      products: Array.from({ length: 12 }, (_, index) => ({ id: `product-${index}`, category_name: 'Men' })),
    });
    const { container } = render(<MemoryRouter><ProductList presetCategory="Men" /></MemoryRouter>);
    await waitFor(() => expect(screen.getAllByTestId('product-product-11')).toHaveLength(2));
    const desktopGrid = container.querySelector('.hidden.lg\\:block');
    expect(desktopGrid?.querySelectorAll('[data-testid^="product-"]')).toHaveLength(12);
  });

  it('keeps featured vendors visible when rotation settings fail to load', async () => {
    getProductsMock.mockResolvedValue({ products: [{ id: 'product-1', category_name: 'Men' }] });
    getFeaturedStorefrontVendorsMock.mockResolvedValue([{
      id: 'vendor-1', business_name: 'Featured Vendor', featured_storefront_image_url: '/uploads/featured.jpg', product_count: 1,
    }]);
    getFeaturedRotationSettingsMock.mockRejectedValue(new Error('settings unavailable'));

    render(<MemoryRouter><ProductList presetCategory="Men" /></MemoryRouter>);

    await waitFor(() => expect(screen.getAllByTestId('vendor-image')).not.toHaveLength(0));
  });

  it('normalizes relative featured vendor image URLs to the API origin', async () => {
    getProductsMock.mockResolvedValue({
      products: [{ id: 'product-1', category_name: 'Men' }],
    });
    getFeaturedStorefrontVendorsMock.mockResolvedValue([{
      id: 'vendor-1',
      business_name: 'Featured Vendor',
      featured_storefront_image_url: '/uploads/featured.jpg',
      product_count: 1,
    }]);

    render(<MemoryRouter><ProductList presetCategory="Men" /></MemoryRouter>);

    await waitFor(() => expect(screen.getAllByTestId('vendor-image')).not.toHaveLength(0));
    expect(screen.getAllByTestId('vendor-image')[0]).toHaveTextContent(
      'http://localhost:8000/uploads/featured.jpg',
    );
  });
});
