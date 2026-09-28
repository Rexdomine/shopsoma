import { beforeEach, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { useCurrencyStore } from './currencyStore';
import { usePreferenceStore } from './preferenceStore';
import Header from '../components/layout/Header';
import Cart from '../pages/cart/Cart';
vi.mock('../context/AuthContext', () => ({ useAuth: () => ({ isAuthenticated: false, user: null }) }));
vi.mock('../components/layout/Layout', () => ({ default: ({ children }: { children: React.ReactNode }) => <>{children}</> }));
vi.mock('../components/modals/EditVariantModal', () => ({ default: () => null }));
vi.mock('../hooks/useWishlistActions', () => ({ useWishlistActions: () => ({ favorites: new Set(), toggleFavorite: vi.fn() }) }));
vi.mock('../services/productService', () => ({ productService: { getProducts: vi.fn(async () => ({ products: [] })) } }));
vi.mock('./cartStore', () => ({ useCartStore: (selector: (state: unknown) => unknown) => selector({
  cart: {
    items: [{ id: 'item', product_id: 'product', quantity: 1, subtotal: 10, price: 10,
      product: { id: 'product', title: 'USD product', currency: 'USD', base_price: 10, images: [] },
      variant: { id: 'variant', size: 'M', color: 'Blue', price: 10 } }],
    summary: { itemCount: 1, subtotal: 10, total: 10 },
  }, updateQuantity: vi.fn(), updateVariant: vi.fn(), removeItem: vi.fn(),
}) }));
beforeEach(() => {
  useCurrencyStore.getState().applyCommerceFeatures({ stripe_enabled: false, usd_switching_enabled: false });
  useCurrencyStore.getState().updateExchangeRates({ USD_TO_NGN: 833, NGN_TO_USD: 1 / 833 });
});
it('hides the header currency control including the opened mobile menu while disabled', () => {
  render(<MemoryRouter><Header /></MemoryRouter>);
  expect(screen.queryByRole('button', { name: 'Change currency' })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Open menu' }));
  expect(screen.queryByText('($) USD')).not.toBeInTheDocument();
  act(() => useCurrencyStore.getState().applyCommerceFeatures({ stripe_enabled: false, usd_switching_enabled: true }));
  fireEvent.click(screen.getByRole('button', { name: 'Change currency' }));
  fireEvent.click(screen.getByRole('button', { name: '($) USD' }));
  expect(useCurrencyStore.getState().currentCurrency).toBe('USD');
  expect(usePreferenceStore.getState().currency).toBe('USD');
});
it('converts an original USD cart amount to NGN instead of relabeling it', async () => {
  usePreferenceStore.getState().setCurrency('USD');
  render(<MemoryRouter><Cart /></MemoryRouter>);
  await waitFor(() => expect(screen.getAllByText(/8,330/).length).toBeGreaterThan(0));
  expect(screen.queryByText('₦10.00')).not.toBeInTheDocument();
});
