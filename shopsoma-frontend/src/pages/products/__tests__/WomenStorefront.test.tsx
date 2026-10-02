import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import WomenStorefront from '../WomenStorefront';
import type { Category } from '../../../types';

const { getPrimaryCategoriesMock, getSubcategoriesMock } = vi.hoisted(() => ({
  getPrimaryCategoriesMock: vi.fn(),
  getSubcategoriesMock: vi.fn(),
}));

vi.mock('../../../services/categoryService', () => ({
  categoryService: {
    getPrimaryCategories: getPrimaryCategoriesMock,
    getSubcategories: getSubcategoriesMock,
  },
}));

vi.mock('../../../components/common/Loading', () => ({
  default: ({ message }: { message?: string }) => <div>{message}</div>,
}));

vi.mock('../ProductList', () => ({
  default: ({
    categoryNav,
    childCategoryOverrides,
    presetCategory,
    initialParams,
  }: {
    categoryNav?: Category[];
    childCategoryOverrides?: Record<string, Category[]>;
    presetCategory?: string;
    initialParams?: { category_id: string };
  }) => (
    <div
      data-testid="women-storefront-mock"
      data-preset={presetCategory}
      data-category-id={initialParams?.category_id}
    >
      <div data-testid="category-nav-names">
        {categoryNav?.map((c) => c.name).join(' | ')}
      </div>
      <div data-testid="has-lingerie-children">
        {String(
          Boolean(
            childCategoryOverrides?.['women-lingerie-pyjamas']?.some(
              (c) => c.name === 'Shapewear'
            )
          )
        )}
      </div>
      <div data-testid="has-sets-children">
        {String(
          Boolean(
            childCategoryOverrides?.['women-sets']?.some(
              (c) => c.name === 'Trouser Sets'
            )
          )
        )}
      </div>
    </div>
  ),
}));

describe('WomenStorefront', () => {
  beforeEach(() => {
    getPrimaryCategoriesMock.mockReset();
    getSubcategoriesMock.mockReset();
    window.sessionStorage.clear();
  });

  it('renders default subcategories including Women’s Lingerie/Pyjamas immediately', async () => {
    getPrimaryCategoriesMock.mockResolvedValue([
      { id: 'women-db-id', name: 'Women', slug: 'women', is_active: true, display_order: 1 },
    ]);
    getSubcategoriesMock.mockResolvedValue([
      { id: 'women-tops-id', name: "Women's Tops", slug: 'women-tops', is_active: true, display_order: 1 },
      { id: 'women-lingerie-id', name: "Women's Lingerie/Pyjamas", slug: 'women-lingerie-pyjamas', is_active: true, display_order: 9 },
      { id: 'women-sets-id', name: "Women's Sets", slug: 'women-sets', is_active: true, display_order: 10 },
    ]);

    render(<WomenStorefront />);

    // Should include Women's Lingerie/Pyjamas in navigation
    const navText = screen.getByTestId('category-nav-names');
    expect(navText).toHaveTextContent("Women's Lingerie/Pyjamas");
    expect(navText).toHaveTextContent("Women's Sets");

    // Child category overrides should be provided
    expect(screen.getByTestId('has-lingerie-children')).toHaveTextContent('true');
    expect(screen.getByTestId('has-sets-children')).toHaveTextContent('true');
  });

  it('merges missing newly added subcategories if API returns older subcategory list', async () => {
    getPrimaryCategoriesMock.mockResolvedValue([
      { id: 'women-db-id', name: 'Women', slug: 'women', is_active: true, display_order: 1 },
    ]);
    // Stale/old API response missing lingerie and sets
    getSubcategoriesMock.mockResolvedValue([
      { id: 'women-tops-id', name: "Women's Tops", slug: 'women-tops', is_active: true, display_order: 1 },
      { id: 'women-dresses-id', name: "Women's Dresses", slug: 'women-dresses', is_active: true, display_order: 2 },
    ]);

    render(<WomenStorefront />);

    await waitFor(() => {
      const navText = screen.getByTestId('category-nav-names');
      expect(navText).toHaveTextContent("Women's Lingerie/Pyjamas");
      expect(navText).toHaveTextContent("Women's Sets");
    });
  });

  it('merges missing subcategories when sessionStorage has older cached data', async () => {
    window.sessionStorage.setItem(
      'shopsoma_subcategories_27b5a940-610d-4243-a796-7e4c63b04060',
      JSON.stringify({
        categories: [
          { id: 'old-tops-id', name: "Women's Tops", slug: 'women-tops', is_active: true, display_order: 1 },
        ],
      })
    );

    getPrimaryCategoriesMock.mockResolvedValue([
      { id: '27b5a940-610d-4243-a796-7e4c63b04060', name: 'Women', slug: 'women', is_active: true, display_order: 1 },
    ]);
    getSubcategoriesMock.mockResolvedValue([]);

    render(<WomenStorefront />);

    const navText = screen.getByTestId('category-nav-names');
    expect(navText).toHaveTextContent("Women's Lingerie/Pyjamas");
    expect(navText).toHaveTextContent("Women's Sets");
  });
});
