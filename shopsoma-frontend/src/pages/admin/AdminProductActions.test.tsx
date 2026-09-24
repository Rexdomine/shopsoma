// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), lockRequest: vi.fn(), error: vi.fn(), success: vi.fn(), warning: vi.fn(), hideToast: vi.fn(), setCurrency: vi.fn(), fetchExchangeRate: vi.fn() }));
vi.mock('../../services/api', () => ({ default: { get: mocks.get, put: mocks.put } }));
vi.mock('../../hooks/useToast', () => ({ useToast: () => ({ toasts: [], error: mocks.error, success: mocks.success, warning: mocks.warning, hideToast: mocks.hideToast }) }));
vi.mock('../../store/currencyStore', () => ({ useCurrencyStore: () => ({ currentCurrency: 'NGN', exchangeRates: {}, setCurrency: mocks.setCurrency, fetchExchangeRate: mocks.fetchExchangeRate }) }));
vi.mock('../../components/common/CurrencySwitcher', () => ({ default: () => null }));
vi.mock('../../components/admin/AdminSidebar', () => ({ default: () => null }));
import AdminProductDetail from './AdminProductDetail';
import AdminProductEdit from './AdminProductEdit';
import AdminProducts from './AdminProducts';

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
    if (url.startsWith('/admin/products?')) return { data: { items: [{ ...product, sku: 'SKU-1', vendor: { id: 'vendor-1', business_name: 'Test Vendor' }, moderated_at: null, moderation_notes: null }], total: 1, page: 1, page_size: 20, total_pages: 1 } };
    throw { response: { status: 404, data: { detail: 'Product not found' } } };
  });
  mocks.put.mockResolvedValue({ data: { message: 'Product updated successfully', product_id: product.id } });
  mocks.lockRequest.mockImplementation(async (_name: string, _options: unknown, callback: (lock: object) => Promise<unknown>) => callback({}));
  Object.defineProperty(navigator, 'locks', { configurable: true, value: { request: mocks.lockRequest } });
  vi.spyOn(console, 'error').mockImplementation(() => {});
});
afterEach(() => { cleanup(); sessionStorage.clear(); localStorage.clear(); vi.restoreAllMocks(); });

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
    await waitFor(() => expect(mocks.put).toHaveBeenCalledWith('/admin/products/product-1/approve', { notes: 'Looks good', expected_updated_at: '2026-09-23T10:00:00Z' }));
    await waitFor(() => expect(mocks.get).toHaveBeenCalledTimes(3));
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
    await waitFor(() => expect(mocks.put).toHaveBeenCalledWith('/admin/products/product-1/reject', { reason: 'The images do not meet quality requirements.', notes: 'Please update photos', expected_updated_at: '2026-09-23T10:00:00Z' }));
    expect((screen.getByLabelText('Rejection Reason *') as HTMLTextAreaElement).value).toContain('quality');
    expect((screen.getByLabelText('Rejection Notes (Optional)') as HTMLTextAreaElement).value).toBe('Please update photos');
  });
  it('denies from the detail page, then shows the server-returned rejected status', async () => {
    mount('view');
    fireEvent.click(await screen.findByRole('button', { name: 'Deny Product' }));
    fireEvent.change(screen.getByLabelText('Rejection Reason *'), { target: { value: '  Product images need correction  ' } });
    mocks.get.mockResolvedValueOnce({ data: { ...product } });
    mocks.get.mockResolvedValueOnce({ data: { ...product, moderation_status: 'rejected' } });
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Deny Product' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(await screen.findByText(/^rejected$/i)).toBeTruthy();
    expect(mocks.put).toHaveBeenCalledWith('/admin/products/product-1/reject', { reason: 'Product images need correction', notes: null, expected_updated_at: '2026-09-23T10:00:00Z' });
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
    await waitFor(() => expect(mocks.put).toHaveBeenCalledTimes(1));
    mocks.get.mockResolvedValueOnce({ data: { ...product, moderation_status: 'approved' } });
    finish({ data: {} });
    expect(await screen.findByText(/^approved$/i)).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Approve Product' })).toBeNull();
  });
  it('does not send a mutation when another tab holds the atomic moderation lock', async () => {
    mocks.lockRequest.mockImplementationOnce(async (_name: string, _options: unknown, callback: (lock: null) => Promise<unknown>) => callback(null));
    mount('view');
    fireEvent.click(await screen.findByRole('button', { name: 'Approve Product' }));
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Approve Product' }));
    await waitFor(() => expect(screen.getByText(/another admin tab is processing/i)).toBeTruthy());
    expect(mocks.put).not.toHaveBeenCalled();
    expect(mocks.lockRequest).toHaveBeenCalledWith('shopsoma-admin-moderation:product-1', { ifAvailable: true }, expect.any(Function));
  });
  it('disables cancellation while waiting for the atomic moderation lock', async () => {
    let releaseLock!: (lock: object | null) => void;
    mocks.lockRequest.mockImplementationOnce((_name: string, _options: unknown, callback: (lock: object | null) => Promise<unknown>) =>
      new Promise(resolve => {
        releaseLock = (lock) => resolve(callback(lock));
      }));
    mount('view');
    fireEvent.click(await screen.findByRole('button', { name: 'Approve Product' }));
    const dialog = screen.getByRole('dialog');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Approve Product' }));
    await waitFor(() => expect(within(dialog).getByRole('button', { name: 'Cancel' })).toBeDisabled());
    expect(mocks.put).not.toHaveBeenCalled();
    releaseLock(null);
    expect(await screen.findByText(/another admin tab is processing/i)).toBeTruthy();
    expect(mocks.put).not.toHaveBeenCalled();
  });

  it('renders structured moderation errors and retains notes for retry', async () => {
    mocks.put.mockRejectedValueOnce({ response: { data: { detail: [{ msg: 'Approval not permitted' }] } } });
    mount('view');
    fireEvent.click(await screen.findByRole('button', { name: 'Approve Product' }));
    fireEvent.change(screen.getByLabelText('Approval Notes (Optional)'), { target: { value: 'Keep this note' } });
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Approve Product' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Approval not permitted');
    expect(screen.getByLabelText('Approval Notes (Optional)')).toHaveValue('Keep this note');
    expect(mocks.get).toHaveBeenCalledTimes(2);
    expect(screen.getByTestId('location')).toHaveTextContent('/admin/products/product-1');
  });
  it.each(['approve', 'deny'] as const)('reconciles a response-less %s failure before allowing another mutation', async action => {
    mocks.put.mockRejectedValueOnce(new Error('Network disconnected'));
    mount('view');
    await screen.findByRole('heading', { name: product.title });
    mocks.get.mockResolvedValueOnce({ data: { ...product } });
    mocks.get.mockResolvedValueOnce({ data: { ...product, moderation_status: action === 'approve' ? 'approved' : 'rejected' } });
    fireEvent.click(screen.getByRole('button', { name: action === 'approve' ? 'Approve Product' : 'Deny Product' }));
    if (action === 'deny') fireEvent.change(screen.getByLabelText('Rejection Reason *'), { target: { value: 'The product does not meet the marketplace requirements.' } });
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: action === 'approve' ? 'Approve Product' : 'Deny Product' }));
    await waitFor(() => expect(mocks.get).toHaveBeenCalledTimes(3));
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(mocks.put).toHaveBeenCalledTimes(1);
  });
  it('keeps an ambiguous outcome locked while GET reconciliation remains pending', async () => {
    mocks.put.mockRejectedValueOnce(new Error('Network disconnected'));
    mocks.get.mockResolvedValueOnce({ data: { ...product } });
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
    expect(mocks.get).toHaveBeenCalledTimes(4);
    expect(within(screen.getByRole('dialog')).getByRole('button', { name: 'Refresh required' })).toBeDisabled();
    mocks.get.mockResolvedValueOnce({ data: { ...product, moderation_status: 'approved' } });
    fireEvent.click(screen.getByRole('button', { name: 'Refresh product status' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  });
  it('closes the moderation dialog when direct reconciliation finds the opposite terminal status', async () => {
    mocks.put.mockRejectedValueOnce(new Error('Network disconnected'));
    mount('view');
    fireEvent.click(await screen.findByRole('button', { name: 'Approve Product' }));
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Approve Product' }));
    mocks.get.mockResolvedValueOnce({ data: { ...product } });
    mocks.get.mockResolvedValueOnce({ data: { ...product, moderation_status: 'rejected' } });
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(screen.getByText(/^rejected$/i)).toBeTruthy();
    expect(screen.queryByText(/Product approval verified/i)).toBeNull();
  });
  it('closes the moderation dialog when reconciliation finds the opposite terminal status', async () => {
    mocks.put.mockRejectedValueOnce(new Error('Network disconnected'));
    mocks.get.mockResolvedValue({ data: { ...product } });
    mount('view');
    fireEvent.click(await screen.findByRole('button', { name: 'Approve Product' }));
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Approve Product' }));
    await waitFor(() => expect(screen.getByText(/still pending/i)).toBeTruthy());
    mocks.get.mockResolvedValueOnce({ data: { ...product, moderation_status: 'rejected' } });
    fireEvent.click(screen.getByRole('button', { name: 'Refresh product status' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(screen.getByText(/^rejected$/i)).toBeTruthy();
    expect(screen.queryByText(/Product approval verified/i)).toBeNull();
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
  it('coordinates an ambiguity lock received from another admin tab', async () => {
    mount('view');
    await screen.findByRole('heading', { name: product.title });
    fireEvent.click(screen.getByRole('button', { name: 'Approve Product' }));
    localStorage.setItem('admin-moderation-outcome-unknown:product-1', JSON.stringify({ cycleSignature: 'Awaiting review\\u0000' }));
    window.dispatchEvent(new StorageEvent('storage', {
      key: 'admin-moderation-outcome-unknown:product-1',
      newValue: localStorage.getItem('admin-moderation-outcome-unknown:product-1'),
      storageArea: localStorage,
    }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(screen.getByRole('button', { name: 'Approve Product' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Deny Product' })).toBeDisabled();
    expect(screen.getByText(/another admin tab/i)).toBeTruthy();
    expect(mocks.put).not.toHaveBeenCalled();
  });
  it('releases a stale ambiguity lock after its bounded lease expires', async () => {
    localStorage.setItem('admin-moderation-outcome-unknown:product-1', JSON.stringify({ cycleSignature: 'old', leaseUntil: Date.now() - 1, owner: 'old-tab' }));
    mount('view');
    await screen.findByRole('heading', { name: product.title });
    expect(screen.getByRole('button', { name: 'Approve Product' })).not.toBeDisabled();
    expect(localStorage.getItem('admin-moderation-outcome-unknown:product-1')).toBeNull();
  });
  it('requires review when pending content changes before confirmation', async () => {
    mocks.put.mockRejectedValueOnce(new Error('Network disconnected'));
    mount('view');
    await screen.findByRole('heading', { name: product.title });
    mocks.get.mockResolvedValueOnce({ data: { ...product, title: 'Admin corrected title', updated_at: '2026-09-24T10:05:00Z' } });
    fireEvent.click(screen.getByRole('button', { name: 'Approve Product' }));
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Approve Product' }));
    expect(await screen.findByText(/changed after it was loaded/i)).toBeTruthy();
    expect(screen.getByRole('dialog')).toBeTruthy();
    expect(within(screen.getByRole('dialog')).getByRole('button', { name: 'Approve Product' })).not.toBeDisabled();
    expect(localStorage.getItem('admin-moderation-outcome-unknown:product-1')).toBeNull();
    expect(mocks.put).not.toHaveBeenCalled();
  });
  it('requires review when an unrelated product field changes before confirmation', async () => {
    mocks.put.mockRejectedValueOnce(new Error('Network disconnected'));
    mount('view');
    await screen.findByRole('heading', { name: product.title });
    mocks.get.mockResolvedValue({ data: { ...product, base_price: product.base_price + 100, updated_at: '2026-09-24T10:06:00Z' } });
    fireEvent.click(screen.getByRole('button', { name: 'Approve Product' }));
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Approve Product' }));
    expect(await screen.findByText(/changed after it was loaded/i)).toBeTruthy();
    expect(screen.getByRole('dialog')).toBeTruthy();
    expect(localStorage.getItem('admin-moderation-outcome-unknown:product-1')).toBeNull();
    expect(mocks.put).not.toHaveBeenCalled();
  });
  it('retries only the GET after successful moderation but failed refresh', async () => {
    mount('view');
    fireEvent.click(await screen.findByRole('button', { name: 'Approve Product' }));
    mocks.get.mockResolvedValueOnce({ data: { ...product } });
    mocks.get.mockRejectedValueOnce(new Error('Read temporarily unavailable'));
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Approve Product' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('moderation action succeeded');
    expect(screen.queryByRole('button', { name: 'Approve Product' })).toBeNull();
    mocks.get.mockResolvedValueOnce({ data: { ...product, moderation_status: 'approved' } });
    fireEvent.click(screen.getByRole('button', { name: 'Refresh product' }));
    expect(await screen.findByText(/^approved$/i)).toBeTruthy();
    expect(screen.queryByRole('alert')).toBeNull();
    expect(mocks.put).toHaveBeenCalledTimes(1);
    expect(mocks.get).toHaveBeenCalledTimes(4);
  });
  it.each(['approved', 'rejected'] as const)('does not show moderation actions for %s products', async status => {
    mocks.get.mockResolvedValue({ data: { ...product, moderation_status: status } });
    mount('view');
    await screen.findByRole('heading', { name: product.title });
    expect(screen.queryByRole('button', { name: 'Approve Product' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Deny Product' })).toBeNull();
  });
  it('reconciles a detail 409 conflict through the authoritative product refresh', async () => {
    mocks.put.mockRejectedValueOnce({ response: { status: 409, data: { detail: 'Product moderation has already been decided' } } });
    mount('view');
    await screen.findByRole('heading', { name: product.title });
    fireEvent.click(screen.getByRole('button', { name: 'Approve Product' }));
    mocks.get.mockResolvedValueOnce({ data: { ...product } });
    mocks.get.mockResolvedValueOnce({ data: { ...product, moderation_status: 'rejected' } });
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Approve Product' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(await screen.findByText(/^rejected$/i)).toBeTruthy();
    expect(mocks.error).toHaveBeenCalledWith(expect.stringContaining('already moderated'), 'Moderation conflict');
    expect(mocks.put).toHaveBeenCalledTimes(1);
  });
  it('preserves conflict context when the detail refresh fails', async () => {
    mocks.put.mockRejectedValueOnce({ response: { status: 409, data: { detail: 'Product moderation has already been decided' } } });
    mount('view');
    await screen.findByRole('heading', { name: product.title });
    fireEvent.click(screen.getByRole('button', { name: 'Approve Product' }));
    mocks.get.mockResolvedValueOnce({ data: { ...product } });
    mocks.get.mockRejectedValueOnce(new Error('Read temporarily unavailable'));
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Approve Product' }));
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent(/already moderated.*current status could not be loaded/i));
    expect(screen.getByRole('alert')).not.toHaveTextContent(/moderation action succeeded/i);
  });
  it.each(['approve', 'reject'] as const)('refreshes the admin list after a %s 409 conflict', async action => {
    mocks.put.mockRejectedValueOnce({ response: { status: 409, data: { detail: 'Product moderation has already been decided' } } });
    render(<MemoryRouter><AdminProducts /></MemoryRouter>);
    await screen.findByText(product.title);
    fireEvent.click(screen.getByTitle(action === 'approve' ? 'Approve Product' : 'Reject Product'));
    if (action === 'reject') {
      fireEvent.change(screen.getByPlaceholderText('Explain why this product cannot be approved (minimum 10 characters)...'), { target: { value: 'Product needs better images' } });
    }
    const confirmName = action === 'approve' ? 'Approve Product' : 'Reject Product';
    fireEvent.click(screen.getAllByRole('button', { name: confirmName })[1]);
    await waitFor(() => expect(mocks.put).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(await screen.findByText(/already moderated.*list was refreshed/i)).toBeTruthy();
    expect(mocks.get.mock.calls.filter(([url]) => String(url).startsWith('/admin/products?')).length).toBeGreaterThanOrEqual(2);
  });
  it('retains an explicit reconciliation state when the list refresh fails after a 409', async () => {
    mocks.put.mockRejectedValueOnce({ response: { status: 409, data: { detail: 'Product moderation has already been decided' } } });
    render(<MemoryRouter><AdminProducts /></MemoryRouter>);
    await screen.findByText(product.title);
    fireEvent.click(screen.getByTitle('Approve Product'));
    mocks.get.mockResolvedValueOnce({ data: { ...product } });
    mocks.get.mockRejectedValueOnce(new Error('List temporarily unavailable'));
    fireEvent.click(screen.getAllByRole('button', { name: 'Approve Product' })[1]);
    await waitFor(() => expect(screen.getByText(/moderation conflict could not be reconciled/i)).toBeTruthy());
    expect(screen.getByTitle('Approve Product')).toBeDisabled();
    expect(screen.getByTitle('Reject Product')).toBeDisabled();
  });
  it('list moderation honors the shared ambiguity marker before issuing a PUT', async () => {
    render(<MemoryRouter><AdminProducts /></MemoryRouter>);
    await screen.findByText(product.title);
    fireEvent.click(screen.getByTitle('Approve Product'));
    localStorage.setItem('admin-moderation-outcome-unknown:product-1', JSON.stringify({
      cycleSignature: `${product.title}\\u0000${product.description}`,
      leaseUntil: Date.now() + 120000,
      owner: 'detail-tab',
    }));
    fireEvent.click(screen.getAllByRole('button', { name: 'Approve Product' })[1]);
    expect(await screen.findByText(/unconfirmed moderation request/i)).toBeTruthy();
    expect(mocks.put).not.toHaveBeenCalled();

    localStorage.clear();
    fireEvent.click(screen.getAllByRole('button', { name: 'Approve Product' })[1]);
    await waitFor(() => expect(mocks.put).toHaveBeenCalledTimes(1));
    expect(mocks.lockRequest).toHaveBeenCalledWith('shopsoma-admin-moderation:product-1', { ifAvailable: true }, expect.any(Function));
  });
  it('list moderation revalidates status inside the lock before issuing a PUT', async () => {
    render(<MemoryRouter><AdminProducts /></MemoryRouter>);
    await screen.findByText(product.title);
    fireEvent.click(screen.getByTitle('Approve Product'));
    mocks.get.mockResolvedValueOnce({ data: { ...product, moderation_status: 'approved' } });
    fireEvent.click(screen.getAllByRole('button', { name: 'Approve Product' })[1]);
    expect(await screen.findByText(/already been moderated/i)).toBeTruthy();
    expect(mocks.put).not.toHaveBeenCalled();
    expect(mocks.lockRequest).toHaveBeenCalledWith('shopsoma-admin-moderation:product-1', { ifAvailable: true }, expect.any(Function));
  });
  it('detail moderation revalidates status inside the lock before issuing a PUT', async () => {
    mount('view');
    await screen.findByRole('heading', { name: product.title });
    fireEvent.click(screen.getByRole('button', { name: 'Approve Product' }));
    mocks.get.mockResolvedValueOnce({ data: { ...product, moderation_status: 'approved' } });
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Approve Product' }));
    expect(await screen.findByText(/^APPROVED$/)).toBeTruthy();
    expect(mocks.put).not.toHaveBeenCalled();
  });
  it('detail moderation refuses a revision changed after the dialog opened', async () => {
    mount('view');
    await screen.findByRole('heading', { name: product.title });
    fireEvent.click(screen.getByRole('button', { name: 'Approve Product' }));
    mocks.get.mockResolvedValueOnce({ data: { ...product, title: 'Vendor revised shirt', updated_at: '2026-09-24T10:05:00Z' } });
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Approve Product' }));
    expect(await screen.findByText(/changed after it was loaded/i)).toBeTruthy();
    expect(screen.getByRole('dialog')).toBeTruthy();
    expect(mocks.put).not.toHaveBeenCalled();
  });
  it('list moderation refuses a revision changed after the dialog opened', async () => {
    render(<MemoryRouter><AdminProducts /></MemoryRouter>);
    await screen.findByText(product.title);
    fireEvent.click(screen.getByTitle('Approve Product'));
    mocks.get.mockResolvedValueOnce({ data: { ...product, title: 'Vendor revised shirt', updated_at: '2026-09-24T10:05:00Z' } });
    fireEvent.click(screen.getAllByRole('button', { name: 'Approve Product' })[1]);
    expect(await screen.findByText(/changed after the approval dialog opened/i)).toBeTruthy();
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(mocks.put).not.toHaveBeenCalled();
  });
  it('list denial validates the trimmed reason length before sending the trimmed payload', async () => {
    render(<MemoryRouter><AdminProducts /></MemoryRouter>);
    await screen.findByText(product.title);
    fireEvent.click(screen.getByTitle('Reject Product'));
    const reason = screen.getByPlaceholderText('Explain why this product cannot be approved (minimum 10 characters)...') as HTMLTextAreaElement;
    fireEvent.change(reason, { target: { value: '        valid      ' } });
    expect(screen.getAllByRole('button', { name: 'Reject Product' })[1]).toBeDisabled();
    fireEvent.change(reason, { target: { value: '  valid rejection reason  ' } });
    fireEvent.click(screen.getAllByRole('button', { name: 'Reject Product' })[1]);
    await waitFor(() => expect(mocks.put).toHaveBeenCalledWith('/admin/products/product-1/reject', { reason: 'valid rejection reason', notes: null, expected_updated_at: '2026-09-23T10:00:00Z' }));
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
