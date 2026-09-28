import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import VendorProducts from './VendorProducts';
import VendorProductView from './VendorProductView';

const mocks = vi.hoisted(() => ({
  getVendorProducts: vi.fn(), getVendorProduct: vi.fn(), duplicateProduct: vi.fn(),
  error: vi.fn(), success: vi.fn(), fetchExchangeRate: vi.fn(),
}));
vi.mock('../../services/productService', () => ({ productService: mocks }));
vi.mock('../../hooks/useToast', () => ({
  useToast: () => ({ error: mocks.error, success: mocks.success, toasts: [], hideToast: vi.fn() }),
}));
vi.mock('../../context/VendorContext', () => ({
  useVendor: () => ({ vendorProfile: { id: 'vendor' }, isLoading: false }),
}));
vi.mock('../../store/currencyStore', () => ({
  useCurrencyStore: () => ({
    currentCurrency: 'USD', setCurrency: vi.fn(), exchangeRates: {}, fetchExchangeRate: mocks.fetchExchangeRate,
  }),
}));
vi.mock('../../components/vendor/VendorSidebar', () => ({ default: () => null }));
vi.mock('../../components/vendor/BulkUploadModal', () => ({ default: () => null }));
vi.mock('../../components/common/CurrencySwitcher', () => ({ default: () => null }));
const product = {
  id: 'source', title: 'Silk dress', currency: 'USD', base_price: 15,
  status: 'active', product_type: 'single', total_stock: 3, moderation_status: 'approved',
  images: [], variations: [], variants: [], created_at: '2026-01-01', updated_at: '2026-01-01',
};
beforeEach(() => {
  vi.clearAllMocks();
  mocks.getVendorProduct.mockResolvedValue(product);
  mocks.getVendorProducts.mockResolvedValue({ products: [product] });
});

function mount(page: 'list' | 'detail') {
  render(
    <MemoryRouter initialEntries={[page === 'list' ? '/vendor/products' : '/vendor/products/source']}>
      <Routes>
        <Route path="/vendor/products" element={<VendorProducts />} />
        <Route path="/vendor/products/:id" element={<VendorProductView />} />
        <Route path="/vendor/products/:id/edit" element={<p>Draft edit page</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe.each(['list', 'detail'] as const)('Duplicate from %s', page => {
  it('blocks repeat clicks and navigates to the saved draft', async () => {
    let resolve!: (value: { id: string }) => void;
    mocks.duplicateProduct.mockReturnValue(new Promise(res => { resolve = res; }));
    mount(page);
    const buttons = await screen.findAllByRole('button', { name: /^Duplicate/ });
    fireEvent.click(buttons[0]);
    fireEvent.click(buttons[0]);
    expect(mocks.duplicateProduct).toHaveBeenCalledTimes(1);
    buttons.forEach(button => expect(button).toBeDisabled());
    await act(async () => resolve({ id: 'new' }));
    expect(await screen.findByText('Draft edit page')).toBeInTheDocument();
  });

  it('explains an uncertain response without retrying', async () => {
    mocks.duplicateProduct.mockRejectedValue(new Error('timeout'));
    mount(page);
    fireEvent.click((await screen.findAllByRole('button', { name: /^Duplicate/ }))[0]);
    await waitFor(() => expect(mocks.error).toHaveBeenCalledWith(
      expect.stringContaining('Refresh your product list before trying again'), 'Duplication Failed',
    ));
    expect(mocks.duplicateProduct).toHaveBeenCalledTimes(1);
    expect(screen.queryByText('Draft edit page')).not.toBeInTheDocument();
  });

  it('shows a definite validation error and restores the controls', async () => {
    mocks.duplicateProduct.mockRejectedValue({ response: { status: 409, data: { detail: 'Source images need repair' } } });
    mount(page);
    const button = (await screen.findAllByRole('button', { name: /^Duplicate/ }))[0];
    fireEvent.click(button);
    await waitFor(() => expect(mocks.error).toHaveBeenCalledWith('Source images need repair', 'Duplication Failed'));
    expect(button).toBeEnabled();
  });
});
