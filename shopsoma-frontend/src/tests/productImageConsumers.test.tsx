import type { ReactNode } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Product, ProductVariant } from '../types';
import { API_BASE_URL, IMAGE_CONFIG } from '../config/constants';
import Cart from '../pages/cart/Cart';
import AddToBagModal from '../components/modals/AddToBagModal';
import EditVariantModal from '../components/modals/EditVariantModal';
import VendorProductView from '../pages/vendor/VendorProductView';

const mocks = vi.hoisted(() => ({
  getVendorProduct: vi.fn(), getProducts: vi.fn(), error: vi.fn(), fetchExchangeRate: vi.fn(),
  cartState: { cart: { items: [] as any[], summary: { subtotal: 100, total: 100, itemCount: 1 } } },
}));
vi.mock('../services/productService', () => ({ productService: mocks }));
vi.mock('../components/layout/Layout', () => ({ default: ({ children }: { children: ReactNode }) => <div>{children}</div> }));
vi.mock('../components/vendor/VendorSidebar', () => ({ default: () => null }));
vi.mock('../components/vendor/DeleteProductModal', () => ({ default: () => null }));
vi.mock('../hooks/useToast', () => ({ useToast: () => ({ toasts: [], error: mocks.error }) }));
vi.mock('../hooks/useWishlistActions', () => ({ useWishlistActions: () => ({ favorites: new Set(), toggleFavorite: vi.fn() }) }));
vi.mock('../store/cartStore', () => ({ useCartStore: (selector: (state: typeof mocks.cartState) => unknown) => selector(mocks.cartState) }));
vi.mock('../store/preferenceStore', () => ({ usePreferenceStore: (selector: (state: { currency: string }) => unknown) => selector({ currency: 'NGN' }) }));
vi.mock('../store/currencyStore', () => ({ useCurrencyStore: (selector?: (state: any) => unknown) => {
  const state = {
    currentCurrency: 'NGN',
    exchangeRates: { NGN: 1, USD: 0.001 },
    fetchExchangeRate: mocks.fetchExchangeRate,
    commerceFeatures: { usd_switching_enabled: false },
  };
  return selector ? selector(state) : state;
} }));
const origin = API_BASE_URL.replace(/\/api\/v\d+\/?$/, '');
const variant = { id: 'v1', size: 'M', color: 'Black', price: 100, stock: 3 } as ProductVariant;
const product = (thumbnail = '/uploads/thumb.jpg', original = '/uploads/original.jpg') => ({
  id: 'p1', title: 'Image regression dress', base_price: 100, currency: 'NGN', total_stock: 3,
  created_at: '2026-01-01', variants: [variant], variations: [],
  images: [{ id: 'i1', image_url: original, thumbnail_url: thumbnail, is_primary: true, display_order: 0 }],
} as unknown as Product);

beforeEach(() => {
  vi.clearAllMocks();
  mocks.getProducts.mockResolvedValue({ products: [] });
});

for (const surface of ['cart', 'add-to-bag', 'edit-variant'] as const) {
  describe(`${surface} image fallback`, () => {
    function view(p: Product) {
      mocks.cartState.cart.items = [{ id: 'c1', product_id: p.id, product: p, variant, quantity: 1, subtotal: 100 }];
      return <MemoryRouter>{surface === 'cart' ? <Cart /> : surface === 'add-to-bag'
        ? <AddToBagModal open product={p} variant={variant} quantity={1} onClose={vi.fn()} />
        : <EditVariantModal open product={p} currentVariant={variant} onClose={vi.fn()} onSave={vi.fn()} />}</MemoryRouter>;
    }
    it('tries the normalized original after thumbnail failure, then stops at the local placeholder', async () => {
      render(view(product()));
      const img = screen.getByAltText('Image regression dress');
      expect(img).toHaveAttribute('src', origin + '/uploads/thumb.jpg');
      fireEvent.error(img);
      expect(img).toHaveAttribute('src', origin + '/uploads/original.jpg');
      fireEvent.error(img);
      expect(img).toHaveAttribute('src', IMAGE_CONFIG.PLACEHOLDER);
      const writes = vi.spyOn(img as HTMLImageElement, 'src', 'set');
      fireEvent.error(img);
      expect(writes).not.toHaveBeenCalled();
      writes.mockRestore();
      await screen.findByAltText('Image regression dress');
    });
    it('preserves a working external original and handles an empty gallery', async () => {
      const rendered = render(view(product('', 'https://cdn.example.test/working.jpg')));
      expect(screen.getByAltText('Image regression dress')).toHaveAttribute('src', 'https://cdn.example.test/working.jpg');
      rendered.rerender(view({ ...product(), images: [] }));
      expect(screen.getByAltText('Image regression dress')).toHaveAttribute('src', IMAGE_CONFIG.PLACEHOLDER);
      await screen.findByAltText('Image regression dress');
    });
    it('resets fallback attempts when product image sources change', async () => {
      const rendered = render(view(product()));
      fireEvent.error(screen.getByAltText('Image regression dress'));
      rendered.rerender(view(product('/uploads/new-thumb.jpg', '/uploads/new-original.jpg')));
      const img = screen.getByAltText('Image regression dress');
      expect(img).toHaveAttribute('src', origin + '/uploads/new-thumb.jpg');
      fireEvent.error(img);
      expect(img).toHaveAttribute('src', origin + '/uploads/new-original.jpg');
      await screen.findByAltText('Image regression dress');
    });
  });
}

describe('vendor detail gallery', () => {
  function view() {
    return render(<MemoryRouter initialEntries={['/vendor/products/p1']}><Routes>
      <Route path="/vendor/products/:id" element={<VendorProductView />} />
    </Routes></MemoryRouter>);
  }
  it('renders overlapping product and variation images once in primary order', async () => {
    const data = { ...product(), images: [
      { ...product().images![0], id: 'other', image_url: 'https://cdn.example.test/working.jpg', thumbnail_url: '', is_primary: false },
      product().images![0],
    ], variations: [
      { images: ['/uploads/original.jpg', origin + '/uploads/original.jpg', 'https://cdn.example.test/working.jpg', '/uploads/variation-only.jpg'] },
      { images: ['/uploads/variation-only.jpg'] },
    ] };
    mocks.getVendorProduct.mockResolvedValue(data);
    view();
    await screen.findByAltText('Product image 1');
    expect(screen.getAllByAltText(/Product image \d/).map(img => img.getAttribute('src'))).toEqual([
      origin + '/uploads/thumb.jpg', 'https://cdn.example.test/working.jpg', origin + '/uploads/variation-only.jpg',
    ]);
    expect(data.images[0].id).toBe('other');
    expect(mocks.getVendorProduct).toHaveBeenCalledWith('p1');
  });
  it('preserves a single-product gallery and the empty state', async () => {
    mocks.getVendorProduct.mockResolvedValue(product('', 'https://cdn.example.test/working.jpg'));
    const first = view();
    expect(await screen.findByAltText('Product image 1')).toHaveAttribute('src', 'https://cdn.example.test/working.jpg');
    expect(screen.getAllByAltText(/Product image \d/)).toHaveLength(1);
    first.unmount();
    mocks.getVendorProduct.mockResolvedValue({ ...product(), images: [] });
    view();
    await screen.findByText('View product details');
    expect(screen.queryByAltText(/Product image \d/)).not.toBeInTheDocument();
  });
});
