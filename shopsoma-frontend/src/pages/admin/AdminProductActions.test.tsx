// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
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
afterEach(() => { cleanup(); sessionStorage.clear(); vi.restoreAllMocks(); });

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
  it('approves a pending detail with optional notes and refreshes in place', async () => {
    mocks.put.mockResolvedValueOnce({ data: { message: 'approved' } });
    mount('view');
    await screen.findByRole('heading', { name: product.title });
    fireEvent.click(screen.getByRole('button', { name: 'Approve Product' }));
    fireEvent.change(screen.getByLabelText('Approval Notes (Optional)'), { target: { value: 'Looks good' } });
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: /^Approve Product$/ }));
    await waitFor(() => expect(mocks.put).toHaveBeenCalledWith('/admin/products/product-1/approve', { notes: 'Looks good' }));
    await waitFor(() => expect(mocks.get).toHaveBeenCalledTimes(2));
    expect(screen.getByTestId('location').textContent).toBe('/admin/products/product-1');
  });
  it('validates denial reason and preserves entered values when rejection fails', async () => {
    mocks.put.mockRejectedValueOnce({ response: { data: { detail: 'Unable to reject' } } });
    mount('view');
    await screen.findByRole('heading', { name: product.title });
    fireEvent.click(screen.getByRole('button', { name: 'Deny Product' }));
    fireEvent.change(screen.getByLabelText('Rejection Reason *'), { target: { value: 'too short' } });
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: /^Deny Product$/ }));
    expect(await screen.findByText('Rejection reason must be at least 10 characters')).toBeTruthy();
    fireEvent.change(screen.getByLabelText('Rejection Reason *'), { target: { value: 'The images do not meet quality requirements.' } });
    fireEvent.change(screen.getByLabelText('Rejection Notes (Optional)'), { target: { value: 'Please update photos' } });
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: /^Deny Product$/ }));
    await waitFor(() => expect(mocks.put).toHaveBeenCalledWith('/admin/products/product-1/reject', { reason: 'The images do not meet quality requirements.', notes: 'Please update photos' }));
    expect((screen.getByLabelText('Rejection Reason *') as HTMLTextAreaElement).value).toContain('quality');
    expect((screen.getByLabelText('Rejection Notes (Optional)') as HTMLTextAreaElement).value).toBe('Please update photos');
  });
  it('denies from the detail page, then shows the server-returned rejected status', async () => {
    mount('view');
    fireEvent.click(await screen.findByRole('button', { name: 'Deny Product' }));
    fireEvent.change(screen.getByLabelText('Rejection Reason *'), { target: { value: '  Product images need correction  ' } });
    mocks.get.mockResolvedValueOnce({ data: { ...product, moderation_status: 'rejected' } });
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Deny Product' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(await screen.findByText(/^rejected$/i)).toBeTruthy();
    expect(mocks.put).toHaveBeenCalledWith('/admin/products/product-1/reject', { reason: 'Product images need correction', notes: null });
    expect(screen.queryByRole('button', { name: 'Approve Product' })).toBeNull();
    expect(screen.getByTestId('location')).toHaveTextContent('/admin/products/product-1');
  });
  it('cancels and escapes without sending a mutation, and focuses the dialog', async () => {
    mount('view');
    fireEvent.click(await screen.findByRole('button', { name: 'Approve Product' }));
    expect(screen.getByLabelText('Approval Notes (Optional)')).toHaveFocus();
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    fireEvent.click(screen.getByRole('button', { name: 'Deny Product' }));
    fireEvent.keyDown(screen.getByLabelText('Rejection Reason *'), { key: 'Escape' });
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(mocks.put).not.toHaveBeenCalled();
  });
  it('disables confirmation and prevents duplicate in-flight approval', async () => {
    let finish!: (value: unknown) => void;
    mocks.put.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
    mount('view');
    fireEvent.click(await screen.findByRole('button', { name: 'Approve Product' }));
    const confirm = within(screen.getByRole('dialog')).getByRole('button', { name: 'Approve Product' });
    fireEvent.click(confirm);
    fireEvent.click(confirm);
    expect(confirm).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled();
    expect(mocks.put).toHaveBeenCalledTimes(1);
    mocks.get.mockResolvedValueOnce({ data: { ...product, moderation_status: 'approved' } });
    finish({ data: {} });
    expect(await screen.findByText(/^approved$/i)).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Approve Product' })).toBeNull();
  });
  it('renders structured moderation errors and retains notes for retry', async () => {
    mocks.put.mockRejectedValueOnce({ response: { data: { detail: [{ msg: 'Approval not permitted' }] } } });
    mount('view');
    fireEvent.click(await screen.findByRole('button', { name: 'Approve Product' }));
    fireEvent.change(screen.getByLabelText('Approval Notes (Optional)'), { target: { value: 'Keep this note' } });
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Approve Product' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Approval not permitted');
    expect(screen.getByLabelText('Approval Notes (Optional)')).toHaveValue('Keep this note');
    expect(mocks.get).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId('location')).toHaveTextContent('/admin/products/product-1');
  });
  it.each(['approve', 'deny'] as const)('reconciles a response-less %s failure before allowing another mutation', async action => {
    mocks.put.mockRejectedValueOnce(new Error('Network disconnected'));
    mount('view');
    await screen.findByRole('heading', { name: product.title });
    mocks.get.mockResolvedValueOnce({ data: { ...product, moderation_status: action === 'approve' ? 'approved' : 'rejected' } });
    fireEvent.click(screen.getByRole('button', { name: action === 'approve' ? 'Approve Product' : 'Deny Product' }));
    if (action === 'deny') fireEvent.change(screen.getByLabelText('Rejection Reason *'), { target: { value: 'The product does not meet the marketplace requirements.' } });
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: action === 'approve' ? 'Approve Product' : 'Deny Product' }));
    await waitFor(() => expect(mocks.get).toHaveBeenCalledTimes(2));
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(mocks.put).toHaveBeenCalledTimes(1);
  });
  it('keeps an ambiguous outcome locked while GET reconciliation remains pending', async () => {
    mocks.put.mockRejectedValueOnce(new Error('Network disconnected'));
    mocks.get.mockResolvedValueOnce({ data: { ...product } });
    mocks.get.mockRejectedValueOnce(new Error('Read unavailable'));
    mount('view');
    fireEvent.click(await screen.findByRole('button', { name: 'Approve Product' }));
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Approve Product' }));
    expect(await screen.findByText(/outcome could not be confirmed/i)).toBeTruthy();
    expect(within(screen.getByRole('dialog')).getByRole('button', { name: 'Refresh required' })).toBeDisabled();
    mocks.get.mockResolvedValueOnce({ data: { ...product, moderation_status: 'pending' } });
    fireEvent.click(screen.getByRole('button', { name: 'Refresh product status' }));
    await waitFor(() => expect(screen.getByText(/still pending/i)).toBeTruthy());
    expect(mocks.put).toHaveBeenCalledTimes(1);
    expect(mocks.get).toHaveBeenCalledTimes(3);
    expect(within(screen.getByRole('dialog')).getByRole('button', { name: 'Refresh required' })).toBeDisabled();
    mocks.get.mockResolvedValueOnce({ data: { ...product, moderation_status: 'approved' } });
    fireEvent.click(screen.getByRole('button', { name: 'Refresh product status' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  });
  it('preserves the ambiguity lock across a detail-page remount', async () => {
    mocks.put.mockRejectedValueOnce(new Error('Network disconnected'));
    mount('view');
    await screen.findByRole('heading', { name: product.title });
    mocks.get.mockResolvedValue({ data: { ...product } });
    fireEvent.click(screen.getByRole('button', { name: 'Approve Product' }));
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Approve Product' }));
    await waitFor(() => expect(screen.getByText(/still pending/i)).toBeTruthy());
    cleanup();
    mount('view');
    await screen.findByRole('heading', { name: product.title });
    expect(screen.getByRole('button', { name: 'Approve Product' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Deny Product' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Refresh product status' })).toBeTruthy();
    mocks.get.mockResolvedValueOnce({ data: { ...product, moderation_status: 'approved' } });
    fireEvent.click(screen.getByRole('button', { name: 'Refresh product status' }));
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Approve Product' })).toBeNull());
    expect(screen.queryByText(/previous moderation request could not be confirmed/i)).toBeNull();
  });
  it('discards an ambiguity lock when reconciliation observes a newer moderation cycle', async () => {
    mocks.put.mockRejectedValueOnce(new Error('Network disconnected'));
    mount('view');
    await screen.findByRole('heading', { name: product.title });
    mocks.get.mockResolvedValueOnce({ data: { ...product, updated_at: '2026-09-24T10:05:00Z' } });
    fireEvent.click(screen.getByRole('button', { name: 'Approve Product' }));
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Approve Product' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(screen.getByRole('button', { name: 'Approve Product' })).not.toBeDisabled();
    expect(screen.getByRole('button', { name: 'Deny Product' })).not.toBeDisabled();
    expect(sessionStorage.getItem('admin-moderation-outcome-unknown:product-1')).toBeNull();
  });
  it('retries only the GET after successful moderation but failed refresh', async () => {
    mount('view');
    fireEvent.click(await screen.findByRole('button', { name: 'Approve Product' }));
    mocks.get.mockRejectedValueOnce(new Error('Read temporarily unavailable'));
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Approve Product' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('moderation action succeeded');
    expect(screen.queryByRole('button', { name: 'Approve Product' })).toBeNull();
    mocks.get.mockResolvedValueOnce({ data: { ...product, moderation_status: 'approved' } });
    fireEvent.click(screen.getByRole('button', { name: 'Refresh product' }));
    expect(await screen.findByText(/^approved$/i)).toBeTruthy();
    expect(screen.queryByRole('alert')).toBeNull();
    expect(mocks.put).toHaveBeenCalledTimes(1);
    expect(mocks.get).toHaveBeenCalledTimes(3);
  });
  it.each(['approved', 'rejected'] as const)('does not show moderation actions for %s products', async status => {
    mocks.get.mockResolvedValue({ data: { ...product, moderation_status: status } });
    mount('view');
    await screen.findByRole('heading', { name: product.title });
    expect(screen.queryByRole('button', { name: 'Approve Product' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Deny Product' })).toBeNull();
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
