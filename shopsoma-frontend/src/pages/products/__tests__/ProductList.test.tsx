import type { ReactNode } from 'react';
import { render, screen, waitFor } from '@testing-library/react';
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
