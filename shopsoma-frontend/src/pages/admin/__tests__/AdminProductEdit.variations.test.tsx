import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import AdminProductEdit from '../AdminProductEdit';

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

vi.mock('../../../services/adminService', () => ({ adminService: adminMocks }));
vi.mock('../../../services/categoryService', () => ({ categoryService: categoryMocks }));
vi.mock('../../../hooks/useToast', () => ({
  useToast: () => ({ toasts: [], error: toastMocks.error, success: toastMocks.success, warning: toastMocks.warning, hideToast: toastMocks.hideToast }),
}));

vi.mock('../../../components/ui/ToastContainer', () => ({
  default: () => <div data-testid="toast-container" />,
}));

vi.mock('../../../components/product/ProductSizeOptionsManager', () => ({
  default: ({ isAdmin }: { isAdmin?: boolean }) => (
    <div data-testid="mock-admin-size-options" data-is-admin={String(isAdmin)}>
      Single Product Size Options
    </div>
  ),
}));

vi.mock('../../../components/product/ProductVariationsManager', () => ({
  default: ({ isAdmin }: { isAdmin?: boolean }) => (
    <div data-testid="mock-admin-variations-manager" data-is-admin={String(isAdmin)}>
      Admin Variations Manager
    </div>
  ),
}));

const mockSingleAdminProduct = {
  id: 'prod-admin-single',
  title: 'Single Cotton Towel',
  description: 'Organic cotton towel',
  category_id: null,
  base_price: 35,
  compare_at_price: 45,
  total_stock: 50,
  status: 'active' as const,
  product_type: 'single' as const,
  made_to_order: false,
  images: [],
  variants: [],
  variations: [],
};

const mockVariableAdminProduct = {
  id: 'prod-admin-var',
  title: 'Variable Linen Pants',
  description: 'Relaxed linen pants',
  category_id: null,
  base_price: 80,
  compare_at_price: 100,
  total_stock: 40,
  status: 'active' as const,
  product_type: 'variable' as const,
  made_to_order: false,
  images: [],
  variants: [],
  variations: [
    {
      id: 'var-admin-1',
      title: 'Beige',
      type: 'color',
      price: 80,
      images: [],
      size_stocks: [],
    },
  ],
};

describe('AdminProductEdit - Variable vs Single Product Flow', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    categoryMocks.getAllCategories.mockResolvedValue([]);
    adminMocks.getProductShopEdits.mockResolvedValue([]);
  });

  it('renders ProductSizeOptionsManager with isAdmin=true for single products', async () => {
    adminMocks.getProduct.mockResolvedValueOnce(mockSingleAdminProduct);

    render(
      <MemoryRouter initialEntries={['/admin/products/prod-admin-single/edit']}>
        <Routes>
          <Route path="/admin/products/:id/edit" element={<AdminProductEdit />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      const singleEl = screen.getByTestId('mock-admin-size-options');
      expect(singleEl).toBeInTheDocument();
      expect(singleEl.getAttribute('data-is-admin')).toBe('true');
      expect(screen.queryByTestId('mock-admin-variations-manager')).not.toBeInTheDocument();
    });
  });

  it('renders ProductVariationsManager with isAdmin=true for variable products', async () => {
    adminMocks.getProduct.mockResolvedValueOnce(mockVariableAdminProduct);

    render(
      <MemoryRouter initialEntries={['/admin/products/prod-admin-var/edit']}>
        <Routes>
          <Route path="/admin/products/:id/edit" element={<AdminProductEdit />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      const varEl = screen.getByTestId('mock-admin-variations-manager');
      expect(varEl).toBeInTheDocument();
      expect(varEl.getAttribute('data-is-admin')).toBe('true');
      expect(screen.queryByTestId('mock-admin-size-options')).not.toBeInTheDocument();
    });
  });
});
