import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import MenStorefront from '../MenStorefront';
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
      data-testid="men-storefront-mock"
      data-preset={presetCategory}
      data-category-id={initialParams?.category_id}
    >
      <div data-testid="category-nav-names">
        {categoryNav?.map((c) => c.name).join(' | ')}
      </div>
      <div data-testid="has-men-sets-children">
        {String(
          Boolean(
            childCategoryOverrides?.['men-sets']?.some(
              (c) => c.name === 'Trouser Sets'
            )
          )
        )}
      </div>
      <div data-testid="has-accessories">
        {String(
          Boolean(
            categoryNav?.some((c) => c.slug === 'men-accessories' || c.name === 'Accessories')
          )
        )}
      </div>
    </div>
  ),
}));

describe('MenStorefront', () => {
  beforeEach(() => {
    getPrimaryCategoriesMock.mockReset();
    getSubcategoriesMock.mockReset();
    window.sessionStorage.clear();
  });

  it('renders default subcategories including Men’s Sets and Accessories immediately', async () => {
    getPrimaryCategoriesMock.mockResolvedValue([
      { id: 'men-db-id', name: 'Men', slug: 'men', is_active: true, display_order: 1 },
    ]);
    getSubcategoriesMock.mockResolvedValue([
      { id: 'men-tops-id', name: 'Tops', slug: 'men-tops', is_active: true, display_order: 1 },
      { id: 'men-sets-id', name: "Men's Sets", slug: 'men-sets', is_active: true, display_order: 4 },
      { id: 'men-accessories-id', name: 'Accessories', slug: 'men-accessories', is_active: true, display_order: 6 },
    ]);

    render(<MenStorefront />);

    const navText = screen.getByTestId('category-nav-names');
    expect(navText).toHaveTextContent("Men's Sets");
    expect(navText).toHaveTextContent('Accessories');
    expect(screen.getByTestId('has-men-sets-children')).toHaveTextContent('true');
    expect(screen.getByTestId('has-accessories')).toHaveTextContent('true');
  });

  it('merges missing subcategories if API returns older list omitting Men’s Sets or Accessories', async () => {
    getPrimaryCategoriesMock.mockResolvedValue([
      { id: 'men-db-id', name: 'Men', slug: 'men', is_active: true, display_order: 1 },
    ]);
    // Stale API response missing Men's Sets and Accessories
    getSubcategoriesMock.mockResolvedValue([
      { id: 'men-tops-id', name: 'Tops', slug: 'men-tops', is_active: true, display_order: 1 },
      { id: 'men-bottoms-id', name: 'Bottoms', slug: 'men-bottoms', is_active: true, display_order: 2 },
    ]);

    render(<MenStorefront />);

    await waitFor(() => {
      const navText = screen.getByTestId('category-nav-names');
      expect(navText).toHaveTextContent("Men's Sets");
      expect(navText).toHaveTextContent('Accessories');
    });
  });
});
