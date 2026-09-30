import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import AdminProductEdit from './AdminProductEdit';

const adminMocks = vi.hoisted(() => ({
  getProduct: vi.fn(),
  getProductShopEdits: vi.fn(),
  updateProduct: vi.fn(),
}));

const categoryMocks = vi.hoisted(() => ({
  getAllCategories: vi.fn(),
}));

const toastMocks = vi.hoisted(() => ({
  error: vi.fn(),
  success: vi.fn(),
  warning: vi.fn(),
  hideToast: vi.fn(),
}));

vi.mock('../../services/adminService', () => ({ adminService: adminMocks }));
vi.mock('../../services/categoryService', () => ({ categoryService: categoryMocks }));
vi.mock('../../hooks/useToast', () => ({
  useToast: () => ({ toasts: [], error: toastMocks.error, success: toastMocks.success, warning: toastMocks.warning, hideToast: toastMocks.hideToast }),
}));

const sampleCategories = [
  { id: 'cat-men', name: 'Men', slug: 'men', parent_id: null, display_order: 1, is_active: true, created_at: '', updated_at: '' },
  { id: 'cat-women', name: 'Women', slug: 'women', parent_id: null, display_order: 2, is_active: true, created_at: '', updated_at: '' },
  { id: 'cat-tops', name: 'Tops', slug: 'men-tops', parent_id: 'cat-men', display_order: 1, is_active: true, created_at: '', updated_at: '' },
  { id: 'cat-bottoms', name: 'Bottoms', slug: 'men-bottoms', parent_id: 'cat-men', display_order: 2, is_active: true, created_at: '', updated_at: '' },
  { id: 'cat-dresses', name: 'Dresses', slug: 'women-dresses', parent_id: 'cat-women', display_order: 1, is_active: true, created_at: '', updated_at: '' },
  { id: 'cat-tshirts', name: 'T-shirts', slug: 'men-tops-tshirts', parent_id: 'cat-tops', display_order: 1, is_active: true, created_at: '', updated_at: '' },
];

const sampleProduct = {
  id: 'prod-123',
  title: 'Classic T-shirt',
  description: 'A great tee',
  category_id: 'cat-tshirts',
  category_name: 'T-shirts',
  base_price: 25,
  compare_at_price: 30,
  total_stock: 50,
  status: 'active' as const,
  images: [],
  variants: [],
  variations: [],
};

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/admin/products/prod-123/edit']}>
      <Routes>
        <Route path="/admin/products/:id/edit" element={<AdminProductEdit />} />
      </Routes>
    </MemoryRouter>
  );
}

describe('AdminProductEdit category management', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    adminMocks.getProduct.mockResolvedValue({ ...sampleProduct });
    adminMocks.getProductShopEdits.mockResolvedValue([]);
    adminMocks.updateProduct.mockResolvedValue({ message: 'Updated' });
    categoryMocks.getAllCategories.mockResolvedValue([...sampleCategories]);
  });

  it('populates primary, sub, and child categories on load based on product category_id', async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByLabelText('Primary Category')).toHaveValue('cat-men');
    });

    expect(screen.getByLabelText('Subcategory')).toHaveValue('cat-tops');
    expect(screen.getByLabelText('Child Category')).toHaveValue('cat-tshirts');
    expect(screen.getByText('cat-tshirts')).toBeInTheDocument();
  });

  it('updates subcategories when primary category changes and updates submitted category_id', async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByLabelText('Primary Category')).toHaveValue('cat-men');
    });

    // Switch primary to Women
    fireEvent.change(screen.getByLabelText('Primary Category'), { target: { value: 'cat-women' } });

    expect(screen.getByLabelText('Primary Category')).toHaveValue('cat-women');
    expect(screen.getByLabelText('Subcategory')).toHaveValue('');

    // Select subcategory "Dresses" under Women
    fireEvent.change(screen.getByLabelText('Subcategory'), { target: { value: 'cat-dresses' } });
    expect(screen.getByLabelText('Subcategory')).toHaveValue('cat-dresses');

    // Submit form
    fireEvent.click(screen.getByRole('button', { name: 'Save Changes' }));

    await waitFor(() => {
      expect(adminMocks.updateProduct).toHaveBeenCalledWith(
        'prod-123',
        expect.objectContaining({
          category_id: 'cat-dresses',
        })
      );
    });
  });

  it('allows clearing the category to null', async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByLabelText('Primary Category')).toHaveValue('cat-men');
    });

    // Clear primary category
    fireEvent.change(screen.getByLabelText('Primary Category'), { target: { value: '' } });
    expect(screen.getByLabelText('Primary Category')).toHaveValue('');

    // Submit form
    fireEvent.click(screen.getByRole('button', { name: 'Save Changes' }));

    await waitFor(() => {
      expect(adminMocks.updateProduct).toHaveBeenCalledWith(
        'prod-123',
        expect.objectContaining({
          category_id: null,
        })
      );
    });
  });
});
