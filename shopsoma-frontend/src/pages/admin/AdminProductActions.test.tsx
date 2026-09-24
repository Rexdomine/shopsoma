// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), error: vi.fn(), success: vi.fn(), warning: vi.fn(), hideToast: vi.fn(), setCurrency: vi.fn() }));
vi.mock('../../services/api', () => ({ default: { get: mocks.get, put: mocks.put } }));
vi.mock('../../hooks/useToast', () => ({ useToast: () => ({ toasts: [], error: mocks.error, success: mocks.success, warning: mocks.warning, hideToast: mocks.hideToast }) }));
vi.mock('../../store/currencyStore', () => ({ useCurrencyStore: () => ({ currentCurrency: 'NGN', exchangeRates: {}, setCurrency: mocks.setCurrency }) }));
vi.mock('../../components/common/CurrencySwitcher', () => ({ default: () => null }));
import AdminProductDetail from './AdminProductDetail';
import AdminProductEdit from './AdminProductEdit';

const product = { id: 'product-1', title: 'Pending linen shirt', description: 'Awaiting review', base_price: 15000, compare_at_price: 18000, currency: 'NGN', total_stock: 8, status: 'draft', moderation_status: 'pending', is_featured: false, category_id: 'category-1', category_name: 'Shirts', vendor_name: 'Test Vendor', created_at: '2026-09-23T10:00:00Z', updated_at: '2026-09-23T10:00:00Z', images: [], variants: [], variations: [], orders_count: 0, views_count: 0 };
function Location() { return <output data-testid="location">{useLocation().pathname}</output>; }
function mount(mode: 'view' | 'edit') {
  render(<MemoryRouter initialEntries={[`/admin/products/product-1${mode === 'edit' ? '/edit' : ''}`]}><Location /><Routes>
    <Route path="/admin/products" element={<p>Admin product list</p>} />
    <Route path="/admin/products/:id" element={<AdminProductDetail />} />
    <Route path="/admin/products/:id/edit" element={<AdminProductEdit />} />
  </Routes></MemoryRouter>);
}
beforeEach(() => {
  vi.clearAllMocks();
  mocks.get.mockImplementation(async (url: string) => {
    if (url === '/admin/products/product-1') return { data: { ...product } };
    throw { response: { status: 404, data: { detail: 'Product not found' } } };
  });
  mocks.put.mockResolvedValue({ data: { message: 'Product updated successfully', product_id: product.id } });
  vi.spyOn(console, 'error').mockImplementation(() => {});
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe('admin product view/edit API boundaries', () => {
  it.each(['view', 'edit'] as const)('%s loads a pending product through admin API without bouncing to list', async mode => {
    mount(mode);
    await waitFor(() => expect(mocks.get).toHaveBeenCalledWith('/admin/products/product-1'));
    await waitFor(() => expect(screen.queryByText('Loading product...')).toBeNull());
    expect(screen.getByTestId('location').textContent).toBe(`/admin/products/product-1${mode === 'edit' ? '/edit' : ''}`);
    expect(screen.queryByText('Admin product list')).toBeNull();
    expect(mocks.get).not.toHaveBeenCalledWith('/products/product-1');
    if (mode === 'edit') expect((await screen.findByLabelText('Product Title *') as HTMLInputElement).value).toBe(product.title);
    else expect((await screen.findAllByText(product.title)).length).toBeGreaterThan(0);
  });
  it('saves using the admin update endpoint and not the vendor endpoint', async () => {
    // Let the legacy read succeed so RED isolates the wrong save endpoint.
    mocks.get.mockResolvedValue({ data: { ...product } });
    mount('edit');
    fireEvent.change(await screen.findByLabelText('Product Title *'), { target: { value: 'Updated linen shirt' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save Changes' }));
    await waitFor(() => expect(mocks.put).toHaveBeenCalledWith('/admin/products/product-1', expect.objectContaining({ title: 'Updated linen shirt' })));
    expect(mocks.put.mock.calls[0][1]).not.toHaveProperty('inventory_quantity');
    expect(mocks.put.mock.calls[0][1]).toMatchObject({ category_id: 'category-1', compare_at_price: 18000 });
    expect(mocks.put.mock.calls[0][1]).not.toHaveProperty('moderation_status');
  });
  it.each(['view', 'edit'] as const)('%s displays a load failure on the current page instead of redirecting', async mode => {
    mocks.get.mockRejectedValue({ response: { status: 403, data: { detail: 'Admin access required' } } });
    mount(mode);
    expect(await screen.findByRole('alert')).toHaveTextContent('Admin access required');
    expect(screen.queryByText('Admin product list')).toBeNull();
    expect(screen.getByRole('button', { name: 'Back to Products' })).toBeTruthy();
  });
  it('keeps edits and renders structured validation failures after a failed save', async () => {
    mocks.get.mockResolvedValue({ data: { ...product } });
    mocks.put.mockRejectedValue({ response: { status: 422, data: { detail: [{ loc: ['body', 'category_id'], msg: 'Invalid category', type: 'value_error' }] } } });
    mount('edit');
    fireEvent.change(await screen.findByLabelText('Product Title *'), { target: { value: 'Preserve this title' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save Changes' }));
    await waitFor(() => expect(mocks.error).toHaveBeenCalledWith(expect.stringContaining('Invalid category'), 'Update Failed'));
    expect((screen.getByLabelText('Product Title *') as HTMLInputElement).value).toBe('Preserve this title');
    expect(screen.getByTestId('location').textContent).toBe('/admin/products/product-1/edit');
  });
});
