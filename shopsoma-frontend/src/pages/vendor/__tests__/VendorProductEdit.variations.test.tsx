import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import VendorProductEdit from '../VendorProductEdit';
import { productService } from '../../../services/productService';

vi.mock('../../../services/productService', () => ({
  productService: {
    getVendorProduct: vi.fn(),
    updateProduct: vi.fn(),
    deleteProductImage: vi.fn(),
    setPrimaryProductImage: vi.fn(),
  },
}));

vi.mock('../../../components/vendor/VendorSidebar', () => ({
  default: () => <nav data-testid="vendor-sidebar">Sidebar</nav>,
}));

vi.mock('../../../components/ui/ToastContainer', () => ({
  default: () => <div data-testid="toast-container" />,
}));

vi.mock('../../../components/product/ProductSizeOptionsManager', () => ({
  default: () => <div data-testid="mock-size-options-manager">Single Product Size Options</div>,
}));

vi.mock('../../../components/product/ProductVariationsManager', () => ({
  default: () => <div data-testid="mock-variations-manager">Variable Product Variations Manager</div>,
}));

const mockSingleProduct = {
  id: 'prod-single-1',
  vendor_id: 'vendor-1',
  title: 'Handmade Silk Blouse',
  description: 'Pure silk blouse',
  base_price: 150,
  compare_at_price: 180,
  total_stock: 10,
  status: 'active' as const,
  product_type: 'single' as const,
  made_to_order: false,
  variants: [],
  variations: [],
  images: [],
  moderation_status: 'pending',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

const mockVariableProduct = {
  id: 'prod-var-2',
  vendor_id: 'vendor-1',
  title: 'Variable Linen Shirt',
  description: 'Pure linen shirt',
  base_price: 90,
  compare_at_price: 110,
  total_stock: 30,
  status: 'active' as const,
  product_type: 'variable' as const,
  made_to_order: false,
  variants: [],
  variations: [
    {
      id: 'var-1',
      title: 'Red',
      type: 'color',
      price: 90,
      images: [],
      size_stocks: [],
    },
  ],
  images: [],
  moderation_status: 'pending',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

describe('VendorProductEdit - Variable vs Single Product Flow', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders ProductSizeOptionsManager for single products preserving existing flow', async () => {
    (productService.getVendorProduct as any).mockResolvedValueOnce(mockSingleProduct);

    render(
      <MemoryRouter initialEntries={['/vendor/products/prod-single-1/edit']}>
        <Routes>
          <Route path="/vendor/products/:id/edit" element={<VendorProductEdit />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByTestId('mock-size-options-manager')).toBeInTheDocument();
      expect(screen.queryByTestId('mock-variations-manager')).not.toBeInTheDocument();
    });
  });

  it('renders ProductVariationsManager for variable products', async () => {
    (productService.getVendorProduct as any).mockResolvedValueOnce(mockVariableProduct);

    render(
      <MemoryRouter initialEntries={['/vendor/products/prod-var-2/edit']}>
        <Routes>
          <Route path="/vendor/products/:id/edit" element={<VendorProductEdit />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByTestId('mock-variations-manager')).toBeInTheDocument();
      expect(screen.queryByTestId('mock-size-options-manager')).not.toBeInTheDocument();
    });
  });
});
