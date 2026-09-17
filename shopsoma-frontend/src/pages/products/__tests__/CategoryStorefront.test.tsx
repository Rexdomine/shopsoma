import { act, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useNavigate } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import CategoryStorefront from '../CategoryStorefront';

const { getAllCategoriesMock } = vi.hoisted(() => ({
  getAllCategoriesMock: vi.fn(),
}));

vi.mock('../../../services/categoryService', () => ({
  categoryService: { getAllCategories: getAllCategoriesMock },
}));
vi.mock('../../../components/common/Loading', () => ({
  default: ({ message }: { message?: string }) => <div>{message}</div>,
}));
vi.mock('../../errors/NotFound', () => ({
  default: () => <div>Not found</div>,
}));
vi.mock('../ProductList', () => ({
  default: ({ presetCategory, heroOverride }: { presetCategory: string; heroOverride?: { body: string } }) => (
    <div>
      <div>{presetCategory} products</div>
      {heroOverride && <div data-testid="category-hero-copy">{heroOverride.body}</div>}
    </div>
  ),
}));

function NavigateToNewCategory() {
  const navigate = useNavigate();
  return <button onClick={() => navigate('/category/new-category')}>Open new category</button>;
}

function renderStorefront() {
  return render(
    <MemoryRouter initialEntries={['/category/old-category']}>
      <NavigateToNewCategory />
      <Routes>
        <Route path="/category/:slug" element={<CategoryStorefront />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('CategoryStorefront', () => {
  beforeEach(() => {
    getAllCategoriesMock.mockReset();
  });

  it('resets the displayed category while a route slug transition is loading', async () => {
    let resolveNewCategory: ((categories: never[]) => void) | undefined;
    getAllCategoriesMock
      .mockResolvedValueOnce([{ id: 'old-id', name: 'Old category', slug: 'old-category', description: '' }])
      .mockReturnValueOnce(new Promise((resolve) => {
        resolveNewCategory = resolve;
      }));

    renderStorefront();
    await waitFor(() => expect(screen.getByText('Old category products')).toBeInTheDocument());

    act(() => screen.getByRole('button', { name: 'Open new category' }).click());

    expect(screen.getByText('Loading category...')).toBeInTheDocument();
    expect(screen.queryByText('Old category products')).not.toBeInTheDocument();

    resolveNewCategory?.([]);
    await waitFor(() => expect(screen.getByText('Not found')).toBeInTheDocument());
  });

  it('uses intentional editorial copy for homepage category storefronts', async () => {
    getAllCategoriesMock.mockResolvedValueOnce([
      { id: 'evening-id', name: 'Evening', slug: 'shop-edits-occasion-wear-evening', description: 'Generic backend description' },
    ]);

    render(
      <MemoryRouter initialEntries={['/category/shop-edits-occasion-wear-evening']}>
        <Routes>
          <Route path="/category/:slug" element={<CategoryStorefront />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByTestId('category-hero-copy')).toHaveTextContent(
      'Polished silhouettes and memorable details for dinners, celebrations and nights that call for something more.',
    ));
  });
});
