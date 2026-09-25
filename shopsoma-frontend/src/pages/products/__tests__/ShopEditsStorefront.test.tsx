import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ShopEditsStorefront from '../ShopEditsStorefront';

const { getAllCategoriesMock, getPrimaryCategoriesMock, getSubcategoriesMock } = vi.hoisted(() => ({
  getAllCategoriesMock: vi.fn(),
  getPrimaryCategoriesMock: vi.fn(),
  getSubcategoriesMock: vi.fn(),
}));

vi.mock('../../../services/categoryService', () => ({
  categoryService: {
    getAllCategories: getAllCategoriesMock,
    getPrimaryCategories: getPrimaryCategoriesMock,
    getSubcategories: getSubcategoriesMock,
  },
}));

vi.mock('../../../components/common/Loading', () => ({
  default: ({ message }: { message?: string }) => <div>{message}</div>,
}));

vi.mock('../ProductList', () => ({
  default: ({ categoryNav, initialParams }: {
    categoryNav: { name: string }[];
    initialParams?: { category_id: string };
  }) => (
    <div data-testid="shop-edits-tabs" data-category-id={initialParams?.category_id}>
      {categoryNav.map((category) => category.name).join('|')}
    </div>
  ),
}));

const category = (id: string, name: string, slug: string, displayOrder: number) => ({
  id,
  name,
  slug,
  display_order: displayOrder,
  is_active: true,
  created_at: '',
  updated_at: '',
});

describe('ShopEditsStorefront', () => {
  beforeEach(() => {
    getAllCategoriesMock.mockReset();
    getPrimaryCategoriesMock.mockReset();
    getSubcategoriesMock.mockReset();
  });

  it('loads only the ordered Occasion Wear leaf tabs beneath Shop Edits', async () => {
    getPrimaryCategoriesMock.mockResolvedValue([
      category('shop-edits-id', 'Shop Edits', 'shop-edits', 1),
    ]);
    getSubcategoriesMock.mockImplementation((parentId: string) => {
      if (parentId === 'shop-edits-id') {
        return Promise.resolve([
          category('seasonal-id', 'Seasonal', 'shop-edits-seasonal', 1),
          category('occasion-wear-id', 'Occasion Wear', 'shop-edits-occasion-wear', 2),
          category('designer-picks-id', 'Designer Picks', 'shop-edits-designer-picks', 3),
        ]);
      }
      return Promise.resolve([
        category('workwear-id', 'Workwear', 'shop-edits-occasion-wear-workwear', 40),
        category('legacy-id', 'Wedding Guest', 'shop-edits-occasion-wear-wedding-guest', 50),
        category('casual-id', 'Casual', 'shop-edits-occasion-wear-casual', 10),
        category('party-id', 'Party', 'shop-edits-occasion-wear-party', 30),
        category('evening-id', 'Evening', 'shop-edits-occasion-wear-evening', 20),
      ]);
    });

    render(<ShopEditsStorefront />);

    await waitFor(() => expect(screen.getByTestId('shop-edits-tabs')).toHaveTextContent(
      'Casual|Evening|Party|Workwear',
    ));
    expect(screen.getByTestId('shop-edits-tabs')).toHaveAttribute('data-category-id', 'shop-edits-id');
    expect(getSubcategoriesMock).toHaveBeenNthCalledWith(1, 'shop-edits-id');
    expect(getSubcategoriesMock).toHaveBeenNthCalledWith(2, 'occasion-wear-id');
    expect(getSubcategoriesMock).toHaveBeenCalledTimes(2);
    expect(getAllCategoriesMock).not.toHaveBeenCalled();
  });

  it('does not fall back to an unscoped product list when Shop Edits is missing', async () => {
    getPrimaryCategoriesMock.mockResolvedValue([]);
    getAllCategoriesMock.mockResolvedValue([]);

    render(<ShopEditsStorefront />);

    expect(await screen.findByRole('alert')).toHaveTextContent('Shop Edits are temporarily unavailable.');
    expect(screen.queryByTestId('shop-edits-tabs')).not.toBeInTheDocument();
    expect(getSubcategoriesMock).not.toHaveBeenCalled();
  });
});
