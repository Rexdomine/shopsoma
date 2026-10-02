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
    window.scrollTo = vi.fn() as unknown as typeof window.scrollTo;
  });

  it('applies the responsive hero position override to the cover image', async () => {
    const { container } = render(
      <MemoryRouter>
        <ProductList heroOverride={{
          title: 'Shop Edits: Curated Discoveries',
          body: 'A rotating curation of elevated essentials, seasonal selections and statement finds.',
          imageUrl: '/images/hero/shop-edits-2088.jpg',
          imagePositionClassName: 'object-center sm:object-top',
        }} />
      </MemoryRouter>,
    );

    await waitFor(() => expect(getProductsMock).toHaveBeenCalled());
    expect(container.querySelector('picture img')).toHaveClass('object-cover', 'object-center', 'sm:object-top');
  });

  it.each([
    [undefined, 'object-center'],
    ['Men', 'object-[40%_25%] max-sm:object-[25%_40%]'],
    ['Women', 'object-[40%_0%] max-sm:object-[36%_42%]'],
  ])('preserves the existing %s hero positioning without an override', async (presetCategory, position) => {
    const { container } = render(<MemoryRouter><ProductList presetCategory={presetCategory} /></MemoryRouter>);

    await waitFor(() => expect(getProductsMock).toHaveBeenCalled());
    const hero = container.querySelector('picture img');
    expect(hero).toHaveClass('object-cover', ...position.split(' '));
    expect(hero).not.toHaveClass('sm:object-top');
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

  it.each([
    ['Casual', 'casual-id', 'casual-product'],
    ['Evening', 'evening-id', 'evening-product'],
    ['Party', 'party-id', 'party-product'],
    ['Workwear', 'workwear-id', 'workwear-product'],
  ] as const)('keeps %s server-filtered Shop Edit products when their normal category differs', async (presetCategory, categoryId, productId) => {
    getProductsMock.mockResolvedValue({
      products: [{ id: productId, category_name: 'Dresses', category_parent_name: 'Women' }],
    });

    render(
      <MemoryRouter>
        <ProductList
          presetCategory={presetCategory}
          initialParams={{ category_id: categoryId }}
          serverFilteredCategory
        />
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getAllByTestId(`product-${productId}`)).not.toHaveLength(0));
    expect(getProductsMock).toHaveBeenCalledWith(expect.objectContaining({ category_id: categoryId }));
  });

  it('applies a later category refinement on a server-filtered Shop Edits route', async () => {
    getProductsMock.mockResolvedValue({
      products: [
        { id: 'dress-product', category_name: 'Dresses' },
        { id: 'top-product', category_name: 'Tops' },
      ],
    });

    render(
      <MemoryRouter>
        <ProductList
          presetCategory="Evening"
          initialParams={{ category_id: 'evening-id' }}
          serverFilteredCategory
        />
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getAllByTestId('product-dress-product')).not.toHaveLength(0));
    expect(screen.getAllByTestId('product-top-product')).not.toHaveLength(0);

    fireEvent.click(screen.getByRole('button', { name: 'REFINE' }));
    fireEvent.click(screen.getByRole('button', { name: 'Dresses' }));

    expect(screen.getAllByTestId('product-dress-product')).not.toHaveLength(0);
    expect(screen.queryAllByTestId('product-top-product')).toHaveLength(0);
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

  it('passes URL search query to productService.getProducts and renders matching products', async () => {
    getProductsMock.mockResolvedValue({
      products: [{ id: 'ejii-tshirt-1', title: 'EJII T-SHIRT', category_name: 'Men', base_price: 30000 }],
      total: 1,
      total_pages: 1,
    });

    render(
      <MemoryRouter initialEntries={['/products?q=EJII+T-SHIRT']}>
        <ProductList />
      </MemoryRouter>
    );

    await waitFor(() => expect(getProductsMock).toHaveBeenCalledWith(
      expect.objectContaining({ search: 'EJII T-SHIRT' })
    ));
    await waitFor(() => expect(screen.getAllByTestId('product-ejii-tshirt-1')).not.toHaveLength(0));
  });

  it('keeps the user on the storefront page when clicking a child category like Earrings', async () => {
    getProductsMock.mockResolvedValue({
      products: [{ id: 'earring-prod-1', title: 'Gold Earrings', category_name: 'Earrings' }],
      total: 1,
      total_pages: 1,
    });

    const categoryNav = [
      { id: 'acc-id', name: 'Accessories', slug: 'accessories', is_active: true, display_order: 1, created_at: '', updated_at: '' },
    ];
    const childCategoryOverrides = {
      'acc-id': [
        { id: 'earrings-id', name: 'Earrings', slug: 'women-accessories-earrings', is_active: true, display_order: 1, created_at: '', updated_at: '' },
      ],
    };

    render(
      <MemoryRouter initialEntries={['/women']}>
        <ProductList
          presetCategory="Women"
          initialParams={{ category_id: 'women-id' }}
          categoryNav={categoryNav}
          childCategoryOverrides={childCategoryOverrides}
        />
      </MemoryRouter>
    );

    await waitFor(() => expect(screen.getByRole('button', { name: 'Accessories' })).toBeInTheDocument());

    // Hover or enter Accessories to reveal child categories
    fireEvent.mouseEnter(screen.getByRole('button', { name: 'Accessories' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Earrings' })).toBeInTheDocument());

    // Click child category Earrings
    fireEvent.click(screen.getByRole('button', { name: 'Earrings' }));

    // Should refetch products for the child category ID without navigating away
    await waitFor(() => expect(getProductsMock).toHaveBeenLastCalledWith(
      expect.objectContaining({ category_id: 'earrings-id' })
    ));
    expect(screen.getByRole('button', { name: 'Accessories' })).toBeInTheDocument();
  });

  it('keeps the user on the storefront page when clicking a child category like Trousers on Bottoms', async () => {
    getProductsMock.mockResolvedValue({
      products: [{ id: 'trouser-prod-1', title: 'Linen Trousers', category_name: 'Trousers' }],
      total: 1,
      total_pages: 1,
    });

    const categoryNav = [
      { id: 'bottoms-id', name: 'Bottoms', slug: 'bottoms', is_active: true, display_order: 1, created_at: '', updated_at: '' },
    ];
    const childCategoryOverrides = {
      'bottoms-id': [
        { id: 'trousers-id', name: 'Trousers', slug: 'women-bottoms-trousers', is_active: true, display_order: 1, created_at: '', updated_at: '' },
      ],
    };

    render(
      <MemoryRouter initialEntries={['/women']}>
        <ProductList
          presetCategory="Women"
          initialParams={{ category_id: 'women-id' }}
          categoryNav={categoryNav}
          childCategoryOverrides={childCategoryOverrides}
        />
      </MemoryRouter>
    );

    await waitFor(() => expect(screen.getByRole('button', { name: 'Bottoms' })).toBeInTheDocument());

    // Hover or enter Bottoms to reveal child categories
    fireEvent.mouseEnter(screen.getByRole('button', { name: 'Bottoms' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Trousers' })).toBeInTheDocument());

    // Click child category Trousers
    fireEvent.click(screen.getByRole('button', { name: 'Trousers' }));

    // Should refetch products for the child category ID without navigating away
    await waitFor(() => expect(getProductsMock).toHaveBeenLastCalledWith(
      expect.objectContaining({ category_id: 'trousers-id' })
    ));
    expect(screen.getByRole('button', { name: 'Bottoms' })).toBeInTheDocument();
  });

  it("resolves child categories for Women's Lingerie/Pyjamas by slug override even when database ID is dynamic", async () => {
    getProductsMock.mockResolvedValue({
      products: [{ id: 'shapewear-prod-1', title: 'Shapewear Bodysuit', category_name: 'Shapewear' }],
      total: 1,
      total_pages: 1,
    });

    const categoryNav = [
      {
        id: 'dynamic-db-uuid-for-lingerie',
        name: "Women's Lingerie/Pyjamas",
        slug: 'women-lingerie-pyjamas',
        is_active: true,
        display_order: 9,
        created_at: '',
        updated_at: '',
      },
    ];

    // Override keyed by slug instead of the runtime dynamic database UUID
    const childCategoryOverrides = {
      'women-lingerie-pyjamas': [
        {
          id: 'shapewear-id',
          name: 'Shapewear',
          slug: 'women-lingerie-shapewear',
          is_active: true,
          display_order: 1,
          created_at: '',
          updated_at: '',
        },
        {
          id: 'bras-id',
          name: 'Bras & Bralettes',
          slug: 'women-lingerie-bras-bralettes',
          is_active: true,
          display_order: 2,
          created_at: '',
          updated_at: '',
        },
      ],
    };

    render(
      <MemoryRouter initialEntries={['/women']}>
        <ProductList
          presetCategory="Women"
          initialParams={{ category_id: 'women-id' }}
          categoryNav={categoryNav}
          childCategoryOverrides={childCategoryOverrides}
        />
      </MemoryRouter>
    );

    await waitFor(() =>
      expect(
        screen.getByRole('button', { name: "Women's Lingerie/Pyjamas" })
      ).toBeInTheDocument()
    );

    // Hover over Women's Lingerie/Pyjamas
    fireEvent.mouseEnter(
      screen.getByRole('button', { name: "Women's Lingerie/Pyjamas" })
    );

    // Child categories defined under slug should be visible
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Shapewear' })).toBeInTheDocument()
    );
    expect(
      screen.getByRole('button', { name: 'Bras & Bralettes' })
    ).toBeInTheDocument();

    // Click Shapewear
    fireEvent.click(screen.getByRole('button', { name: 'Shapewear' }));

    await waitFor(() =>
      expect(getProductsMock).toHaveBeenLastCalledWith(
        expect.objectContaining({ category_id: 'shapewear-id' })
      )
    );

    // Parent tab should remain active with border-primary
    expect(
      screen.getByRole('button', { name: "Women's Lingerie/Pyjamas" })
    ).toHaveClass('border-primary');
  });

  it('initializes page from the ?page query parameter and renders products for that page directly', async () => {
    const products = Array.from({ length: 24 }, (_, index) => ({
      id: `prod-${index + 1}`,
      title: `Product ${index + 1}`,
      category_name: 'Men',
    }));
    getProductsMock.mockResolvedValue({
      products,
      total: 24,
      total_pages: 1,
    });

    render(
      <MemoryRouter initialEntries={['/products?page=2']}>
        <ProductList />
      </MemoryRouter>
    );

    // Products on page 2 (index 12 to 23 -> prod-13 to prod-24)
    await waitFor(() => expect(screen.getAllByTestId('product-prod-13')).not.toHaveLength(0));
    expect(screen.queryByTestId('product-prod-1')).not.toBeInTheDocument();

    const page2Button = screen.getByRole('button', { name: '2' });
    expect(page2Button).toHaveClass('border-primary', 'bg-primary', 'text-white');
  });

  it('updates rendered products when clicking pagination page buttons', async () => {
    const products = Array.from({ length: 24 }, (_, index) => ({
      id: `prod-${index + 1}`,
      title: `Product ${index + 1}`,
      category_name: 'Men',
    }));
    getProductsMock.mockResolvedValue({
      products,
      total: 24,
      total_pages: 1,
    });

    render(
      <MemoryRouter initialEntries={['/products']}>
        <ProductList />
      </MemoryRouter>
    );

    await waitFor(() => expect(screen.getAllByTestId('product-prod-1')).not.toHaveLength(0));

    const page2Button = screen.getByRole('button', { name: '2' });
    fireEvent.click(page2Button);

    await waitFor(() => expect(screen.getAllByTestId('product-prod-13')).not.toHaveLength(0));
    expect(screen.queryByTestId('product-prod-1')).not.toBeInTheDocument();
  });

  it('resets page to 1 when a filter is changed from a paginated view', async () => {
    const products = Array.from({ length: 24 }, (_, index) => ({
      id: `prod-${index + 1}`,
      title: `Product ${index + 1}`,
      category_name: index < 15 ? 'Shirts' : 'Trousers',
    }));
    getProductsMock.mockResolvedValue({
      products,
      total: 24,
      total_pages: 1,
    });

    render(
      <MemoryRouter initialEntries={['/products?page=2']}>
        <ProductList />
      </MemoryRouter>
    );

    await waitFor(() => expect(screen.getAllByTestId('product-prod-13')).not.toHaveLength(0));

    // Open refine/filter menu
    fireEvent.click(screen.getByRole('button', { name: 'REFINE' }));
    fireEvent.click(screen.getByRole('button', { name: 'Shirts' }));

    // Should reset to page 1
    await waitFor(() => expect(screen.getAllByTestId('product-prod-1')).not.toHaveLength(0));
    const page1Button = screen.getByRole('button', { name: '1' });
    expect(page1Button).toHaveClass('border-primary', 'bg-primary', 'text-white');
  });
});
