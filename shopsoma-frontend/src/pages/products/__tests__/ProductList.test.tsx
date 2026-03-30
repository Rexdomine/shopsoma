import type { ReactNode } from 'react';
import { render, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, beforeEach, vi } from 'vitest';
import ProductList from '../ProductList';

const { getProductsMock, getSubcategoriesMock } = vi.hoisted(() => ({
  getProductsMock: vi.fn(),
  getSubcategoriesMock: vi.fn(),
}));

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
  default: () => <div>Product</div>,
}));

vi.mock('../../../components/products/VendorShowcaseCard', () => ({
  default: () => <div>Vendor</div>,
}));

describe('ProductList', () => {
  beforeEach(() => {
    getProductsMock.mockReset();
    getSubcategoriesMock.mockReset();
    getProductsMock.mockResolvedValue({ products: [] });
    getSubcategoriesMock.mockResolvedValue([]);
  });

  it('refetches when initialParams change', async () => {
    const { rerender } = render(
      <MemoryRouter>
        <ProductList />
      </MemoryRouter>
    );

    await waitFor(() => expect(getProductsMock).toHaveBeenCalledTimes(1));

    rerender(
      <MemoryRouter>
        <ProductList initialParams={{ category_id: 'men-id' }} />
      </MemoryRouter>
    );

    await waitFor(() => expect(getProductsMock).toHaveBeenCalledTimes(2));

    expect(getProductsMock.mock.calls[1][0]).toEqual(
      expect.objectContaining({ category_id: 'men-id' })
    );
  });
});
