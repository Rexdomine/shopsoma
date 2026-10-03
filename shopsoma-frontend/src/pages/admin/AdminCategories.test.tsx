import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import AdminCategories from './AdminCategories';

const categoryMocks = vi.hoisted(() => ({
  getAdminCategories: vi.fn(),
  getPrimaryCategories: vi.fn(),
  getSubcategories: vi.fn(),
  createCategory: vi.fn(),
  updateCategory: vi.fn(),
  deleteCategory: vi.fn(),
}));

const toastMocks = vi.hoisted(() => ({
  error: vi.fn(),
  success: vi.fn(),
  warning: vi.fn(),
  hideToast: vi.fn(),
}));

vi.mock('../../services/categoryService', () => ({ categoryService: categoryMocks }));
vi.mock('../../hooks/useToast', () => ({
  useToast: () => ({ toasts: [], error: toastMocks.error, success: toastMocks.success, warning: toastMocks.warning, hideToast: toastMocks.hideToast }),
}));
vi.mock('../../components/admin/AdminSidebar', () => ({ default: () => <div data-testid="admin-sidebar" /> }));

const mockCategories = [
  {
    id: 'cat-men',
    name: 'Men',
    slug: 'men',
    parent_id: null,
    parent_name: null,
    level: 'primary' as const,
    display_order: 1,
    is_active: true,
    children_count: 1,
    created_at: '2026-10-01T00:00:00Z',
    updated_at: '2026-10-01T00:00:00Z',
  },
  {
    id: 'cat-tops',
    name: 'Tops',
    slug: 'men-tops',
    parent_id: 'cat-men',
    parent_name: 'Men',
    level: 'subcategory' as const,
    display_order: 1,
    is_active: true,
    children_count: 1,
    created_at: '2026-10-01T00:00:00Z',
    updated_at: '2026-10-01T00:00:00Z',
  },
  {
    id: 'cat-tshirts',
    name: 'T-Shirts',
    slug: 'men-tops-t-shirts',
    parent_id: 'cat-tops',
    parent_name: 'Tops',
    level: 'child' as const,
    display_order: 1,
    is_active: true,
    children_count: 0,
    created_at: '2026-10-01T00:00:00Z',
    updated_at: '2026-10-01T00:00:00Z',
  },
];

describe('AdminCategories page', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    categoryMocks.getAdminCategories.mockResolvedValue([...mockCategories]);
    categoryMocks.getPrimaryCategories.mockResolvedValue([mockCategories[0]]);
    categoryMocks.getSubcategories.mockResolvedValue([mockCategories[1]]);
  });

  it('renders stats, table, and categories correctly', async () => {
    render(
      <MemoryRouter>
        <AdminCategories />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText('Category Management')).toBeInTheDocument();
    });

    // Check categories in table
    expect(screen.getAllByText('Men').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Tops').length).toBeGreaterThan(0);
    expect(screen.getByText('T-Shirts')).toBeInTheDocument();

    // Check level badges
    expect(screen.getAllByText('Primary').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Subcategory').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Child Category').length).toBeGreaterThan(0);
  });

  it('filters by category level tabs', async () => {
    render(
      <MemoryRouter>
        <AdminCategories />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getAllByText('Men').length).toBeGreaterThan(0);
    });

    // Click "Primary" filter
    fireEvent.click(screen.getByRole('button', { name: 'Primary' }));

    expect(screen.getAllByText('Men').length).toBeGreaterThan(0);
    expect(screen.queryByText('Tops')).not.toBeInTheDocument();
    expect(screen.queryByText('T-Shirts')).not.toBeInTheDocument();

    // Click "Subcategories" filter
    fireEvent.click(screen.getByRole('button', { name: 'Subcategories' }));

    expect(screen.getAllByText('Tops').length).toBeGreaterThan(0);
    expect(screen.queryByText('T-Shirts')).not.toBeInTheDocument();
  });

  it('allows opening create modal for Primary Category', async () => {
    categoryMocks.createCategory.mockResolvedValue({
      id: 'cat-new-kids',
      name: 'Kids',
      slug: 'kids',
      parent_id: null,
      level: 'primary',
      display_order: 3,
      is_active: true,
      created_at: '',
      updated_at: '',
    });

    render(
      <MemoryRouter>
        <AdminCategories />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText('Category Management')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: 'Add Primary Category' }));

    expect(screen.getByRole('heading', { name: 'Add Primary Category' })).toBeInTheDocument();

    // Enter name
    fireEvent.change(screen.getByPlaceholderText('e.g., Kids, Beauty, Home & Living'), {
      target: { value: 'Kids' },
    });

    // Submit
    fireEvent.click(screen.getByRole('button', { name: 'Create Category' }));

    await waitFor(() => {
      expect(categoryMocks.createCategory).toHaveBeenCalledWith(
        expect.objectContaining({
          name: 'Kids',
          parent_id: null,
        })
      );
    });
  });

  it('allows deleting a category', async () => {
    categoryMocks.deleteCategory.mockResolvedValue({});

    render(
      <MemoryRouter>
        <AdminCategories />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText('T-Shirts')).toBeInTheDocument();
    });

    // Find delete buttons
    const deleteButtons = screen.getAllByTitle('Delete Category');
    fireEvent.click(deleteButtons[2]); // click T-Shirts delete

    expect(screen.getByRole('heading', { name: 'Delete Category' })).toBeInTheDocument();
    expect(screen.getByText(/Are you sure you want to delete/)).toBeInTheDocument();

    // Confirm deletion via modal's button (the last Delete Category button on the page)
    const deleteBtns = screen.getAllByRole('button', { name: 'Delete Category' });
    const confirmBtn = deleteBtns[deleteBtns.length - 1];
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(categoryMocks.deleteCategory).toHaveBeenCalledWith('cat-tshirts');
    });
  });
});
