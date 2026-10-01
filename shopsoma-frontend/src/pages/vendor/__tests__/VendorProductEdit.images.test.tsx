import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import VendorProductEdit from '../VendorProductEdit';
import { productService } from '../../../services/productService';

vi.mock('../../../services/productService', () => ({
  productService: {
    getVendorProduct: vi.fn(),
    deleteProductImage: vi.fn(),
    uploadImage: vi.fn(),
    addProductImage: vi.fn(),
    updateProduct: vi.fn(),
  },
}));

vi.mock('../../../components/vendor/VendorSidebar', () => ({
  default: () => <nav data-testid="vendor-sidebar">Sidebar</nav>,
}));

vi.mock('../../../components/ui/ToastContainer', () => ({
  default: () => <div data-testid="toast-container" />,
}));

const mockProductBase = {
  id: 'prod-123',
  vendor_id: 'vendor-456',
  title: 'Handmade Silk Blouse',
  description: 'Pure silk blouse',
  base_price: 150,
  compare_price: 180,
  stock_quantity: 10,
  status: 'active' as const,
  is_active: true,
  tags: [],
  made_to_order: false,
  production_timeline: '',
  has_variants: false,
  variants: [],
  category_id: 'cat-1',
  category_name: 'Tops',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  images: [
    {
      id: 'img-1',
      product_id: 'prod-123',
      image_url: 'https://example.com/image1.jpg',
      thumbnail_url: 'https://example.com/thumb1.jpg',
      is_primary: true,
      display_order: 0,
      created_at: '2026-01-01T00:00:00Z',
    },
    {
      id: 'img-2',
      product_id: 'prod-123',
      image_url: 'https://example.com/image2.jpg',
      thumbnail_url: 'https://example.com/thumb2.jpg',
      is_primary: false,
      display_order: 1,
      created_at: '2026-01-01T00:00:00Z',
    },
  ],
};

function renderComponent(productId = 'prod-123') {
  return render(
    <MemoryRouter initialEntries={[`/vendor/products/${productId}/edit`]}>
      <Routes>
        <Route path="/vendor/products/:id/edit" element={<VendorProductEdit />} />
      </Routes>
    </MemoryRouter>
  );
}

describe('VendorProductEdit - Image Management before & after approval', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('allows image deletion and uploading when product is pending approval', async () => {
    vi.mocked(productService.getVendorProduct).mockResolvedValue({
      ...mockProductBase,
      moderation_status: 'pending',
    } as any);
    vi.mocked(productService.deleteProductImage).mockResolvedValue({ message: 'Deleted' } as any);
    vi.mocked(productService.uploadImage).mockResolvedValue({
      original: 'https://example.com/new.jpg',
      thumbnail: 'https://example.com/new-thumb.jpg',
      storage_keys: ['products/new.jpg'],
    } as any);
    vi.mocked(productService.addProductImage).mockResolvedValue({
      id: 'img-3',
      product_id: 'prod-123',
      image_url: 'https://example.com/new.jpg',
      thumbnail_url: 'https://example.com/new-thumb.jpg',
      is_primary: false,
      display_order: 2,
    } as any);

    renderComponent();

    // Wait for product details to load
    await waitFor(() => {
      expect(screen.getByDisplayValue('Handmade Silk Blouse')).toBeInTheDocument();
    });

    // Upload button should be available
    const uploadButton = screen.getByRole('button', { name: /upload images/i });
    expect(uploadButton).toBeInTheDocument();

    // Locked banner should NOT be present
    expect(screen.queryByText(/images are locked/i)).not.toBeInTheDocument();

    // Delete buttons should be present for each image
    const deleteButtons = screen.getAllByRole('button', { name: /delete image/i });
    expect(deleteButtons).toHaveLength(2);

    // Delete the second image
    fireEvent.click(deleteButtons[1]);
    await waitFor(() => {
      expect(productService.deleteProductImage).toHaveBeenCalledWith('prod-123', 'img-2');
    });

    // Upload a new image
    const file = new File(['dummy'], 'blouse.png', { type: 'image/png' });
    const hiddenFileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
    expect(hiddenFileInput).toBeInTheDocument();

    fireEvent.change(hiddenFileInput, { target: { files: [file] } });

    await waitFor(() => {
      expect(productService.uploadImage).toHaveBeenCalledWith(file, 'products', true);
      expect(productService.addProductImage).toHaveBeenCalledWith('prod-123', expect.objectContaining({
        image_url: 'https://example.com/new.jpg',
        thumbnail_url: 'https://example.com/new-thumb.jpg',
      }));
    });
  });

  it('locks image modification when product is approved by admin', async () => {
    vi.mocked(productService.getVendorProduct).mockResolvedValue({
      ...mockProductBase,
      moderation_status: 'approved',
    } as any);

    renderComponent();

    // Wait for product details to load
    await waitFor(() => {
      expect(screen.getByDisplayValue('Handmade Silk Blouse')).toBeInTheDocument();
    });

    // Upload button should NOT be rendered
    expect(screen.queryByRole('button', { name: /upload images/i })).not.toBeInTheDocument();

    // Delete buttons should NOT be rendered
    expect(screen.queryByRole('button', { name: /delete image/i })).not.toBeInTheDocument();

    // Locked notice banner should be displayed
    expect(screen.getByText(/images are locked/i)).toBeInTheDocument();
    expect(
      screen.getByText(/This product has already been approved by the admin/i)
    ).toBeInTheDocument();
  });
});
