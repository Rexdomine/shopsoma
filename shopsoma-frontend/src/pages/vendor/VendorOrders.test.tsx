import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  getVendorOrders: vi.fn(),
  exportOrdersToCSV: vi.fn(),
  hideToast: vi.fn(),
  fetchExchangeRate: vi.fn(),
  setCurrency: vi.fn(),
}));

vi.mock('../../components/vendor/VendorSidebar', () => ({
  default: () => <div data-testid="vendor-sidebar" />,
}));

vi.mock('../../components/ui/ToastContainer', () => ({
  default: () => null,
}));

vi.mock('../../components/common/CurrencySwitcher', () => ({
  default: () => <div data-testid="currency-switcher" />,
}));

vi.mock('../../hooks/useToast', () => ({
  useToast: () => ({
    toasts: [],
    hideToast: mocks.hideToast,
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

vi.mock('../../services/orderService', () => ({
  getVendorOrders: mocks.getVendorOrders,
  exportOrdersToCSV: mocks.exportOrdersToCSV,
}));

import VendorOrders, { countVendorOrderBuckets } from './VendorOrders';
import type { VendorOrder } from '../../services/orderService';

const makeOrder = (id: string, fulfillment_status: string): VendorOrder => ({
  id,
  order_number: `SHP-${id}`,
  items: [
    {
      id: `item-${id}`,
      order_id: id,
      product_id: 'prod-1',
      product_title: 'Kaftan',
      variant_details: null,
      unit_price: 10000,
      quantity: 1,
      subtotal: 10000,
      commission_rate: 12.5,
      commission_amount: 1250,
      vendor_payout: 8750,
      fulfillment_status,
      created_at: '2026-11-20T10:00:00Z',
      pickup: null,
    },
  ],
  vendor_business_name: 'Kester Club',
  customer_name: 'Jane Doe',
  customer_email: 'jane@example.com',
  shipping_address: null,
  payment_status: 'paid',
  fulfillment_status,
  created_at: '2026-11-20T10:00:00Z',
  confirmed_at: null,
});

describe('VendorOrders status bucket counts', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(console, 'log').mockImplementation(() => {});
  });

  it('excludes picked_up, in_transit, and out_for_delivery from Pending Orders', () => {
    const counts = countVendorOrderBuckets([
      makeOrder('1', 'order_received'),
      makeOrder('2', 'preparing_for_pickup'),
      makeOrder('3', 'pickup_scheduled'),
      makeOrder('4', 'picked_up'),
      makeOrder('5', 'in_transit'),
      makeOrder('6', 'out_for_delivery'),
      makeOrder('7', 'delivered'),
      makeOrder('8', 'cancelled'),
      makeOrder('9', 'delivery_failed'),
    ]);

    expect(counts).toEqual({
      pendingCount: 3,
      inTransitCount: 3,
      completedCount: 2,
    });
  });

  it('renders separate Pending Orders, In Transit, and Completed Orders counts', async () => {
    mocks.getVendorOrders.mockResolvedValue({
      orders: [
        makeOrder('1', 'order_received'),
        makeOrder('2', 'pickup_scheduled'),
        makeOrder('3', 'picked_up'),
        makeOrder('4', 'in_transit'),
        makeOrder('5', 'out_for_delivery'),
        makeOrder('6', 'delivered'),
      ],
      total: 6,
      page: 1,
      page_size: 20,
      total_pages: 1,
    });

    render(
      <MemoryRouter>
        <VendorOrders />
      </MemoryRouter>
    );

    expect(await screen.findByText(/Pending Orders:\s*2/i)).toBeInTheDocument();
    expect(screen.getByText(/In Transit:\s*3/i)).toBeInTheDocument();
    expect(screen.getByText(/Completed Orders:\s*1/i)).toBeInTheDocument();
  });
});
