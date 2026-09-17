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
  default: ({ presetCategory }: { presetCategory: string }) => <div>{presetCategory} products</div>,
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
});
