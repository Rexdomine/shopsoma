import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import AdminProductEdit from './AdminProductEdit';

const mocks = vi.hoisted(() => ({
  getProduct: vi.fn(),
  getProductShopEdits: vi.fn(),
  updateProduct: vi.fn(),
  updateProductImage: vi.fn(),
  deleteProductImage: vi.fn(),
  createProductImage: vi.fn(),
  uploadProductImage: vi.fn(),
}));

vi.mock('../../services/adminService', () => ({ adminService: mocks }));
vi.mock('../../services/productService', () => ({ productService: { uploadImage: vi.fn() } }));

const product = {
  id: 'product-1', title: 'Silk Dress', description: 'A dress', category_id: null,
  base_price: 99, compare_at_price: null, total_stock: 2, status: 'active',
  moderation_status: 'approved', moderation_notes: null,
  images: [
    { id: 'image-1', image_url: 'https://example.com/one.jpg', thumbnail_url: null, alt_text: 'front', display_order: 0, is_primary: true },
    { id: 'image-2', image_url: 'https://example.com/two.jpg', thumbnail_url: null, alt_text: 'back', display_order: 1, is_primary: false },
  ],
};

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/admin/products/product-1/edit']}>
      <Routes><Route path="/admin/products/:id/edit" element={<AdminProductEdit />} /></Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  Object.defineProperty(window, 'localStorage', { configurable: true, value: { clear: vi.fn(), getItem: vi.fn(), setItem: vi.fn(), removeItem: vi.fn() } });
  Object.defineProperty(window, 'sessionStorage', { configurable: true, value: { clear: vi.fn(), getItem: vi.fn(), setItem: vi.fn(), removeItem: vi.fn() } });
  vi.clearAllMocks();
  mocks.getProduct.mockResolvedValue({ ...product });
  mocks.getProductShopEdits.mockResolvedValue([]);
  mocks.updateProductImage.mockResolvedValue({});
  mocks.deleteProductImage.mockResolvedValue(undefined);
});

describe('admin product image gallery', () => {
  it('does not expose ordering controls for the primary image', async () => {
    renderPage();
    expect(await screen.findByRole('heading', { name: 'Product Images' })).toBeInTheDocument();
    expect(screen.getByAltText('front')).toBeInTheDocument();
    expect(screen.getByAltText('back')).toBeInTheDocument();

    expect(screen.queryByRole('button', { name: 'Move image 1 up' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Move image 1 down' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Move image 2 up' })).toBeEnabled();
    expect(screen.queryByRole('button', { name: 'Move image 2 down' })).not.toBeInTheDocument();
  });

  it('reports a saved image mutation when the canonical refresh is pending and can retry it', async () => {
    mocks.getProduct.mockImplementationOnce(async () => ({ ...product }))
      .mockImplementationOnce(async () => { throw new Error('refresh unavailable'); })
      .mockResolvedValue({ ...product });
    renderPage();

    fireEvent.click(await screen.findByRole('button', { name: 'Move image 2 up' }));
    await waitFor(() => expect(mocks.updateProductImage).toHaveBeenCalledWith('product-1', 'image-2', { display_order: 0 }));
    expect(await screen.findByRole('status')).toHaveTextContent(/saved/i);
    expect(screen.getByRole('button', { name: /refresh product images/i })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /refresh product images/i }));
    await waitFor(() => expect(mocks.getProduct).toHaveBeenCalledTimes(3));
    expect(screen.queryByRole('button', { name: /refresh product images/i })).not.toBeInTheDocument();
  });

  it('sends confirmed delete mutations', async () => {
    renderPage();
    expect(await screen.findByRole('heading', { name: 'Product Images' })).toBeInTheDocument();

    vi.spyOn(window, 'confirm').mockReturnValue(true);
    fireEvent.click(screen.getByRole('button', { name: 'Delete image 2' }));
    await waitFor(() => expect(mocks.deleteProductImage).toHaveBeenCalledWith('product-1', 'image-2'));
  });

  it('shows the empty-state upload affordance and uploads selected files', async () => {
    mocks.getProduct.mockResolvedValue({ ...product, images: [] });
    mocks.uploadProductImage.mockResolvedValue({ image_url: 'https://example.com/uploaded.jpg', thumbnail_url: null });
    renderPage();
    expect(await screen.findByText(/No product images yet/)).toBeInTheDocument();
    const input = screen.getByLabelText('Upload product images');
    const file = new File(['image'], 'dress.jpg', { type: 'image/jpeg' });
    fireEvent.change(input, { target: { files: [file] } });
    await waitFor(() => expect(mocks.uploadProductImage).toHaveBeenCalledWith('product-1', file));
    expect(mocks.createProductImage).not.toHaveBeenCalled();
  });
});
