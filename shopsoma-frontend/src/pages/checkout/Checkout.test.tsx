import type { ReactNode } from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  getAddresses: vi.fn(),
  calculateShipping: vi.fn(),
  reviewOrder: vi.fn(),
  createOrder: vi.fn(),
  createCheckoutEstimate: vi.fn(),
  selectCheckoutEstimateOption: vi.fn(),
  initializePayment: vi.fn(),
  verifyPayment: vi.fn(),
  clearCart: vi.fn(),
  auth: {
    isAuthenticated: true,
    user: { id: 'customer-1', email: 'buyer@example.com', full_name: 'Buyer', phone_number: '08012345678' },
  },
  preference: { currency: 'NGN', setCurrency: vi.fn() },
  currencyState: { exchangeRates: { NGN: 1, USD: 0.000625 } },
  cartState: {
    cart: {
      items: [{
        id: 'cart-1', product_id: 'product-1', quantity: 1, price: 60000, subtotal: 60000,
        product: { id: 'product-1', title: 'Dress', currency: 'NGN', base_price: 60000 },
        variant: { id: 'default-product-1', price: 60000 },
      }],
      summary: { subtotal: 60000, discount: 0, shipping: 0, tax: 0, total: 60000, itemCount: 1 },
    },
  },
}));

vi.mock('../../components/layout/Layout', () => ({
  default: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}));
vi.mock('../../components/payment/StripePaymentForm', () => ({
  default: () => <div>Stripe form</div>,
}));
vi.mock('@stripe/stripe-js', () => ({ loadStripe: vi.fn(() => Promise.resolve(null)) }));
vi.mock('@stripe/react-stripe-js', () => ({
  Elements: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}));
vi.mock('../../context/AuthContext', () => ({
  useAuth: () => mocks.auth,
}));
vi.mock('../../store/preferenceStore', () => ({
  usePreferenceStore: () => mocks.preference,
}));
vi.mock('../../store/currencyStore', () => ({
  useCurrencyStore: (selector: (state: typeof mocks.currencyState) => unknown) =>
    selector(mocks.currencyState),
}));
vi.mock('../../store/cartStore', () => ({
  useCartStore: (selector: (state: typeof mocks.cartState) => unknown) => selector(mocks.cartState),
}));
vi.mock('../../services/cartService', () => ({ CartService: { clearCart: mocks.clearCart } }));
vi.mock('../../services/checkoutService', () => ({
  checkoutService: {
    getAddresses: mocks.getAddresses,
    calculateShipping: mocks.calculateShipping,
    reviewOrder: mocks.reviewOrder,
    createOrder: mocks.createOrder,
    createCheckoutEstimate: mocks.createCheckoutEstimate,
    selectCheckoutEstimateOption: mocks.selectCheckoutEstimateOption,
    validatePromoCode: vi.fn(),
  },
}));
vi.mock('../../services/paymentService', () => ({
  paymentService: {
    initializePayment: mocks.initializePayment,
    verifyPayment: mocks.verifyPayment,
  },
  buildPaystackWidgetConfig: vi.fn(),
}));

import Checkout from './Checkout';

const address = {
  id: 'address-1', user_id: 'customer-1', full_name: 'Buyer', phone_number: '08012345678',
  address_line1: '1 Test Street', city: 'Lagos', state: 'Lagos', country: 'Nigeria',
  address_type: 'shipping', is_default: true, created_at: '2026-01-01', updated_at: '2026-01-01',
};
const rate = {
  id: 'legacy-rate-1', name: 'Standard', description: 'Legacy review rate', base_rate: 2500,
  country: 'Nigeria', state: 'Lagos', min_delivery_days: 3, max_delivery_days: 5,
};
const review = {
  summary: { currency: 'NGN', subtotal: 60000, shipping_cost: 2500, tax_amount: 0, discount_amount: 0, total_amount: 62500, items_count: 1 },
  items: [],
};
const order = {
  id: 'order-1', order_number: 'SHP-1', customer_id: 'customer-1', currency: 'NGN',
  subtotal: 60000, shipping_cost: 2500, tax_amount: 0, discount_amount: 0, total_amount: 62500,
  payment_status: 'pending', fulfillment_status: 'pending', created_at: '2026-01-01', items: [],
  workflow_cohort: 'domestic_checkout_v1', checkout_access_mode: 'authenticated',
};
const estimate = {
  id: 'estimate-1', order_id: 'order-1', currency: 'NGN', expires_at: '2099-01-01T00:00:00Z',
  server_payable_total: '62500.00', selected_option: null,
  options: [{
    id: 'option-1', option_key: 'standard', service_code: 'static_standard', service_label: 'Standard delivery',
    amount: '2500.00', currency: 'NGN', min_delivery_days: 3, max_delivery_days: 5,
  }],
};

async function reachPaymentStep() {
  render(<MemoryRouter><Checkout /></MemoryRouter>);
  await waitFor(() => expect(mocks.getAddresses).toHaveBeenCalled());
  fireEvent.click(screen.getByRole('button', { name: 'Continue' }));
  await screen.findByText('Standard');
  const continueButtons = screen.getAllByRole('button', { name: 'Continue' });
  fireEvent.click(continueButtons[continueButtons.length - 1]);
  await waitFor(() => expect(mocks.reviewOrder).toHaveBeenCalled());
  fireEvent.click(screen.getByRole('radio', { name: /Stripe/ }));
  fireEvent.click(screen.getAllByRole('button', { name: 'Purchase' })[0]);
  await waitFor(() => expect(mocks.createOrder).toHaveBeenCalled());
}

describe('Checkout M5 sequencing and recovery', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal('alert', vi.fn());
    vi.stubGlobal('crypto', { randomUUID: vi.fn(() => `id-${Math.random()}`) });
    mocks.getAddresses.mockResolvedValue({ addresses: [address] });
    mocks.calculateShipping.mockResolvedValue({ available_rates: [rate], recommended_rate: rate });
    mocks.reviewOrder.mockResolvedValue(review);
    mocks.createOrder.mockResolvedValue(order);
    mocks.createCheckoutEstimate.mockResolvedValue(estimate);
    mocks.selectCheckoutEstimateOption.mockResolvedValue({ ...estimate, selected_option: estimate.options[0] });
    mocks.initializePayment.mockResolvedValue({
      status: true, message: 'ready', payment_gateway: 'stripe', reference: 'server-ref',
      amount: '62500.00', amount_minor: 6250000, currency: 'NGN',
      provider_payload: { client_secret: 'secret', payment_intent_id: 'pi-1' },
    });
  });

  it('creates the order then estimate and waits for explicit server option selection before payment', async () => {
    await reachPaymentStep();

    expect(mocks.createCheckoutEstimate).toHaveBeenCalledWith('order-1', expect.stringMatching(/^estimate-/), undefined);
    expect(mocks.initializePayment).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'Continue to payment' })).toBeDisabled();

    fireEvent.click(screen.getByRole('button', { name: 'Select Standard delivery' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Continue to payment' })).toBeEnabled());
    expect(mocks.initializePayment).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Continue to payment' }));

    await waitFor(() => expect(mocks.initializePayment).toHaveBeenCalledWith({
      order_id: 'order-1', email: 'buyer@example.com', payment_gateway: 'stripe',
      callback_url: `${window.location.origin}/payment/verify`,
    }, undefined));
    expect(mocks.createOrder.mock.invocationCallOrder[0]).toBeLessThan(mocks.createCheckoutEstimate.mock.invocationCallOrder[0]);
    expect(mocks.createCheckoutEstimate.mock.invocationCallOrder[0]).toBeLessThan(mocks.initializePayment.mock.invocationCallOrder[0]);
  });

  it('offers truthful estimate recovery after the order is persisted and estimate creation fails', async () => {
    mocks.createCheckoutEstimate.mockRejectedValueOnce({ response: { status: 503, data: { detail: 'temporarily unavailable' } } });
    await reachPaymentStep();

    expect(mocks.createOrder).toHaveBeenCalledTimes(1);
    expect(mocks.initializePayment).not.toHaveBeenCalled();
    expect(await screen.findByRole('button', { name: 'Retry delivery options' })).toBeEnabled();

    fireEvent.click(screen.getByRole('button', { name: 'Retry delivery options' }));
    expect(await screen.findByRole('button', { name: 'Select Standard delivery' })).toBeEnabled();
    expect(mocks.createOrder).toHaveBeenCalledTimes(1);
    expect(mocks.createCheckoutEstimate).toHaveBeenCalledTimes(2);
  });

  it('keeps a 503 payment initialization visibly incomplete and retryable', async () => {
    mocks.initializePayment.mockRejectedValueOnce({ response: { status: 503 } });
    await reachPaymentStep();
    fireEvent.click(screen.getByRole('button', { name: 'Select Standard delivery' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Continue to payment' }));

    await waitFor(() => expect(alert).toHaveBeenCalledWith(expect.stringMatching(/not complete.*retry/i)));
    expect(screen.getByRole('button', { name: 'Continue to payment' })).toBeEnabled();
    expect(screen.queryByText('Stripe form')).not.toBeInTheDocument();
  });
});
