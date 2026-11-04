import type { ReactNode } from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import Designers from '../Designers';
import DesignerStorefront from '../DesignerStorefront';

const { listDesignersMock, getDesignerMock, getProductsMock, getSubcategoriesMock } = vi.hoisted(() => ({
  listDesignersMock: vi.fn(),
  getDesignerMock: vi.fn(),
  getProductsMock: vi.fn(),
  getSubcategoriesMock: vi.fn(),
}));

vi.mock('../../../services/designerService', async () => {
  const actual = await vi.importActual<typeof import('../../../services/designerService')>(
    '../../../services/designerService',
  );
  return {
    ...actual,
    designerService: {
      listDesigners: listDesignersMock,
      getDesigner: getDesignerMock,
    },
  };
});

vi.mock('../../../services/productService', () => ({
  productService: {
    getProducts: getProductsMock,
  },
}));

vi.mock('../../../services/categoryService', () => ({
  categoryService: {
    getSubcategories: getSubcategoriesMock,
  },
}));

vi.mock('../../../services/featuredStorefrontService', () => ({
  getFeaturedStorefrontVendors: vi.fn().mockResolvedValue([]),
}));

vi.mock('../../../services/settingsService', () => ({
  getFeaturedRotationSettings: vi.fn().mockResolvedValue({ rotation_minutes: 10 }),
}));

vi.mock('../../../hooks/useWishlistActions', () => ({
  useWishlistActions: () => ({
    favorites: new Set(),
    toggleFavorite: vi.fn(),
    loadingIds: new Set(),
  }),
}));

vi.mock('../../../store/preferenceStore', () => ({
  usePreferenceStore: (selector: (state: { interest: null }) => unknown) =>
    selector({ interest: null }),
}));

vi.mock('../../../components/layout/Layout', () => ({
  default: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}));

vi.mock('../../../components/common/Loading', () => ({
  default: ({ message }: { message?: string }) => <div>{message}</div>,
}));

vi.mock('../../../components/products/ProductCard', () => ({
  default: ({ product }: { product: { id: string; title: string } }) => (
    <div data-testid={`product-${product.id}`}>{product.title}</div>
  ),
}));

describe('Designers Directory and Storefront', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.sessionStorage.clear();
    window.scrollTo = vi.fn() as unknown as typeof window.scrollTo;
    getProductsMock.mockResolvedValue({ products: [], total: 0, total_pages: 1 });
    getSubcategoriesMock.mockResolvedValue([]);
  });

  it('renders the Shop by Designer photoshoot banner, alphabetical directory grid, A-Z filter, name search, and storefront links', async () => {
    listDesignersMock.mockResolvedValue([
      {
        id: 'designer-zara',
        business_name: 'Zara Atelier',
        business_description: 'Contemporary resort wear',
        logo_url: null,
        featured_storefront_image_url: '/uploads/vendors/zara/campaign.jpg',
        image_url: '/uploads/vendors/zara/campaign.jpg',
        campaign_image_url: '/uploads/vendors/zara/campaign.jpg',
        total_products: 4,
        published_products_count: 4,
        total_orders: 10,
        categories: [],
        created_at: '2026-01-01T00:00:00Z',
      },
      {
        id: 'designer-amaka',
        business_name: 'Amaka Studio',
        business_description: 'Handwoven luxury',
        logo_url: 'https://cdn.shopsoma.com/amaka-logo.jpg',
        featured_storefront_image_url: null,
        image_url: 'https://cdn.shopsoma.com/amaka-editorial.jpg',
        campaign_image_url: 'https://cdn.shopsoma.com/amaka-editorial.jpg',
        total_products: 6,
        published_products_count: 6,
        total_orders: 15,
        categories: [],
        created_at: '2026-01-02T00:00:00Z',
      },
    ]);

    const { container } = render(
      <MemoryRouter initialEntries={['/designers']}>
        <Designers />
      </MemoryRouter>,
    );

    expect(await screen.findByRole('heading', { name: 'Shop by Designer' })).toBeInTheDocument();
    expect(container.querySelector('picture img')).toHaveAttribute(
      'src',
      '/images/hero/campaign/campaign-exterior-desktop.webp',
    );

    // Cards are sorted alphabetically (Amaka Studio first, then Zara Atelier)
    const designerHeadingElements = screen.getAllByRole('heading', { level: 2 });
    expect(designerHeadingElements.map((el) => el.textContent)).toEqual([
      'Amaka Studio',
      'Zara Atelier',
    ]);

    // Links point to each designer's storefront
    expect(screen.getByTestId('designer-card-designer-amaka')).toHaveAttribute(
      'href',
      '/designers/designer-amaka',
    );
    expect(screen.getByTestId('designer-card-designer-zara')).toHaveAttribute(
      'href',
      '/designers/designer-zara',
    );

    // Filter alphabetically by clicking 'Z'
    fireEvent.click(screen.getByRole('button', { name: 'Filter by letter Z' }));
    expect(screen.queryByText('Amaka Studio')).not.toBeInTheDocument();
    expect(screen.getByText('Zara Atelier')).toBeInTheDocument();

    // Reset to 'All'
    fireEvent.click(screen.getByRole('button', { name: 'All' }));
    expect(screen.getByText('Amaka Studio')).toBeInTheDocument();
    expect(screen.getByText('Zara Atelier')).toBeInTheDocument();

    // Search by designer name
    const searchInput = screen.getByLabelText('Search designers by name');
    fireEvent.change(searchInput, { target: { value: 'amaka' } });
    expect(screen.getByText('Amaka Studio')).toBeInTheDocument();
    expect(screen.queryByText('Zara Atelier')).not.toBeInTheDocument();
  });

  it('renders a designer storefront with campaign image, brand description, categories, and published products', async () => {
    getDesignerMock.mockResolvedValue({
      id: 'designer-amaka',
      business_name: 'Amaka Studio',
      business_description: 'Handwoven luxury rooted in Lagos craftsmanship.',
      logo_url: 'https://cdn.shopsoma.com/amaka-logo.jpg',
      featured_storefront_image_url: 'https://cdn.shopsoma.com/amaka-campaign.jpg',
      image_url: 'https://cdn.shopsoma.com/amaka-campaign.jpg',
      campaign_image_url: 'https://cdn.shopsoma.com/amaka-campaign.jpg',
      total_products: 2,
      published_products_count: 2,
      total_orders: 5,
      categories: [
        {
          id: 'cat-dresses',
          name: 'Dresses',
          slug: 'dresses',
          display_order: 1,
          is_active: true,
        },
        {
          id: 'cat-outerwear',
          name: 'Outerwear',
          slug: 'outerwear',
          display_order: 2,
          is_active: true,
        },
      ],
      created_at: '2026-01-02T00:00:00Z',
    });

    getProductsMock.mockResolvedValue({
      products: [
        {
          id: 'prod-silk-kaftan',
          title: 'Silk Kaftan',
          base_price: 85000,
          currency: 'NGN',
          category_name: 'Dresses',
          vendor_id: 'designer-amaka',
          vendor_name: 'Amaka Studio',
          created_at: '2026-02-01T00:00:00Z',
        },
      ],
      total: 1,
      total_pages: 1,
    });

    const { container } = render(
      <MemoryRouter initialEntries={['/designers/designer-amaka']}>
        <Routes>
          <Route path="/designers/:designerId" element={<DesignerStorefront />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByRole('heading', { name: 'Amaka Studio' })).toBeInTheDocument();
    expect(
      screen.getByText('Handwoven luxury rooted in Lagos craftsmanship.'),
    ).toBeInTheDocument();
    expect(container.querySelector('picture img')).toHaveAttribute(
      'src',
      'https://cdn.shopsoma.com/amaka-campaign.jpg',
    );

    // Product categories are shown as tabs
    expect(screen.getByRole('button', { name: 'Dresses' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Outerwear' })).toBeInTheDocument();

    // Published products for this designer are loaded and rendered
    await waitFor(() =>
      expect(getProductsMock).toHaveBeenCalledWith(
        expect.objectContaining({
          vendor_id: 'designer-amaka',
        }),
      ),
    );
    const productCards = await screen.findAllByTestId('product-prod-silk-kaftan');
    expect(productCards.length).toBeGreaterThan(0);
    expect(productCards[0]).toHaveTextContent('Silk Kaftan');
  });

  it('fails closed and renders NotFound when a designer is inactive or unapproved', async () => {
    getDesignerMock.mockRejectedValue(new Error('404 Designer not found'));

    render(
      <MemoryRouter initialEntries={['/designers/unapproved-designer']}>
        <Routes>
          <Route path="/designers/:designerId" element={<DesignerStorefront />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByText(/Page Not Found/i)).toBeInTheDocument();
    expect(getProductsMock).not.toHaveBeenCalled();
  });
});
