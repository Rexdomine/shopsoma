import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  getOrderDetail: vi.fn(),
  runShadowQuote: vi.fn(),
  updateOrderStatus: vi.fn(),
  updateShippingInfo: vi.fn(),
  cancelOrder: vi.fn(),
  processRefund: vi.fn(),
  success: vi.fn(),
  error: vi.fn(),
  warning: vi.fn(),
  hideToast: vi.fn(),
  fetchExchangeRate: vi.fn(),
  setCurrency: vi.fn(),
}));

vi.mock('../../components/admin/AdminSidebar', () => ({
  default: () => <div data-testid="admin-sidebar" />,
}));

vi.mock('../../components/common/CurrencySwitcher', () => ({
  default: () => <div data-testid="currency-switcher" />,
}));

vi.mock('../../hooks/useToast', () => ({
  useToast: () => ({
    toasts: [],
    hideToast: mocks.hideToast,
    success: mocks.success,
    error: mocks.error,
    warning: mocks.warning,
  }),
}));

vi.mock('../../store/currencyStore', () => ({
  useCurrencyStore: () => ({
    currentCurrency: 'NGN',
    setCurrency: mocks.setCurrency,
    exchangeRates: {},
    fetchExchangeRate: mocks.fetchExchangeRate,
  }),
}));

vi.mock('../../utils/pricing', () => ({
  formatPriceWithConversion: (amount: number, currency: string) => `${currency} ${amount}`,
}));

vi.mock('../../utils/orderStatusMessages', () => ({
  getStatusBadgeConfig: () => ({ label: 'Order received', className: 'bg-gray-100 text-gray-900' }),
}));

vi.mock('../../services/adminOrderService', () => ({
  getOrderDetail: mocks.getOrderDetail,
  updateOrderStatus: mocks.updateOrderStatus,
  updateShippingInfo: mocks.updateShippingInfo,
  cancelOrder: mocks.cancelOrder,
  processRefund: mocks.processRefund,
  runShadowQuote: mocks.runShadowQuote,
}));

import AdminOrderDetail from './AdminOrderDetail';
import type { OrderDetail, ShadowQuoteResult } from '../../services/adminOrderService';

const baseOrder = (): OrderDetail => ({
  id: 'order-1',
  order_number: '1001',
  customer: { id: 'customer-1', email: 'customer@example.com', first_name: 'Jane', last_name: 'Doe', phone: '+2348000000000' },
  currency: 'NGN',
  shipping_address: {
    id: 'addr-1',
    full_name: 'Jane Doe',
    phone: '+2348000000000',
    street_address: '12 Broad Street',
    city: 'Lagos',
    state: 'Lagos',
    country: 'NG',
    postal_code: '100001',
  },
  billing_address: undefined,
  subtotal: 1000,
  shipping_cost: 200,
  tax_amount: 0,
  discount_amount: 0,
  total_amount: 1200,
  payment_status: 'paid',
  fulfillment_status: 'order_received',
  delivery_provider: undefined,
  tracking_number: undefined,
  estimated_delivery_date: undefined,
  delivered_at: undefined,
  customer_notes: undefined,
  admin_notes: undefined,
  created_at: '2026-09-02T10:00:00Z',
  updated_at: '2026-09-02T10:00:00Z',
  confirmed_at: undefined,
  cancelled_at: undefined,
  cancellation_reason: undefined,
  items: [
    {
      id: 'item-1',
      product_id: 'product-1',
      product_title: 'Dress',
      product_image_url: undefined,
      variant_details: {},
      unit_price: 1000,
      currency: 'NGN',
      quantity: 1,
      subtotal: 1000,
      commission_rate: 0,
      commission_amount: 0,
      vendor_payout: 1000,
      fulfillment_status: 'order_received',
      vendor: { id: 'vendor-1', business_name: 'Vendor One', contact_email: 'vendor@example.com', contact_phone: '+2348000000001' },
    },
  ],
  pickups: [],
  ready_packages: [{ id: 'pkg-1', current_version: 1, hub_id: 'hub-1', ready_at: '2026-09-02T09:00:00Z' }],
});

const failedResult = (): ShadowQuoteResult => ({
  order_id: 'order-1',
  shadow_quote_id: 'shadow-1',
  result_kind: 'failed',
  environment: 'sandbox',
  adapter_version: '1',
  provider: 'dhl',
  offers_count: 0,
  offers_redacted: [],
  gate_status: { sandbox: true },
  quoted_at: '2026-09-02T10:05:00Z',
  note: 'Carrier rejected the request',
});

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/admin/orders/order-1']}>
      <Routes>
        <Route path="/admin/orders/:orderId" element={<AdminOrderDetail />} />
      </Routes>
    </MemoryRouter>
  );
}

describe('AdminOrderDetail shadow quote result handling', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.getOrderDetail.mockResolvedValue(baseOrder());
  });

  it('shows failed shadow quotes as errors instead of success', async () => {
    mocks.runShadowQuote.mockResolvedValue(failedResult());

    renderPage();

    await screen.findByText('Order #1001');
    fireEvent.click(screen.getByRole('button', { name: 'Run DHL Sandbox Shadow Quote' }));

    await waitFor(() => {
      expect(mocks.runShadowQuote).toHaveBeenCalledWith('order-1', 'pkg-1');
    });
    await waitFor(() => {
      expect(mocks.error).toHaveBeenCalledWith('DHL sandbox shadow quote failed: Carrier rejected the request');
    });
    expect(mocks.success).not.toHaveBeenCalledWith(expect.stringContaining('shadow quote recorded'));

    const failedNote = await screen.findByText('Carrier rejected the request');
    const card = failedNote.closest('div.rounded-lg');
    expect(card?.className).toContain('border-red-200');
    expect(card?.className).toContain('bg-red-50');
    expect(screen.getByText('failed · 0 offer(s)').className).toContain('text-red-900');
  });
});
