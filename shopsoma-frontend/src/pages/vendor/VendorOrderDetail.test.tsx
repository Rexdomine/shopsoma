import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  getVendorOrder: vi.fn(),
  markVendorOrderItemReadyForPickup: vi.fn(),
  success: vi.fn(),
  error: vi.fn(),
  hideToast: vi.fn(),
}));

vi.mock('../../components/vendor/VendorSidebar', () => ({
  default: () => <div data-testid="vendor-sidebar" />,
}));

vi.mock('../../components/ui/ToastContainer', () => ({
  default: () => null,
}));

vi.mock('../../hooks/useToast', () => ({
  useToast: () => ({
    toasts: [],
    hideToast: mocks.hideToast,
    success: mocks.success,
    error: mocks.error,
  }),
}));

vi.mock('../../hooks/useCurrency', () => ({
  useCurrency: () => ({
    currentCurrency: 'NGN',
    setCurrency: vi.fn(),
    formatBasePrice: (amount: number) => `NGN ${amount}`,
    getCurrencySymbol: () => '₦',
    fetchExchangeRate: vi.fn(),
  }),
}));

vi.mock('../../services/orderService', () => ({
  getVendorOrder: mocks.getVendorOrder,
  markVendorOrderItemReadyForPickup: mocks.markVendorOrderItemReadyForPickup,
}));

import VendorOrderDetail from './VendorOrderDetail';
import type { VendorOrder, VendorOrderItem } from '../../services/orderService';

const item = (overrides: Partial<VendorOrderItem>): VendorOrderItem => ({
  id: 'item-1',
  order_id: 'order-1',
  product_id: 'product-1',
  product_title: 'Kaftan',
  variant_details: null,
  unit_price: 1000,
  quantity: 1,
  subtotal: 1000,
  commission_rate: 15,
  commission_amount: 150,
  vendor_payout: 850,
  fulfillment_status: 'order_received',
  created_at: '2026-10-01T10:00:00Z',
  pickup: null,
  made_to_order: false,
  ready_for_pickup_at: null,
  readiness_state: null,
  ...overrides,
});

const order = (items: VendorOrderItem[], paymentStatus = 'paid'): VendorOrder => ({
  id: 'order-1',
  order_number: 'SHP-1001',
  items,
  vendor_business_name: 'Vendor A',
  customer_name: 'Jane Doe',
  customer_email: 'jane@example.com',
  shipping_address: null,
  payment_status: paymentStatus,
  fulfillment_status: 'order_received',
  created_at: '2026-10-01T10:00:00Z',
  confirmed_at: null,
});

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/vendor/orders/order-1']}>
      <Routes>
        <Route path="/vendor/orders/:id" element={<VendorOrderDetail />} />
      </Routes>
    </MemoryRouter>
  );
}

describe('VendorOrderDetail made-to-order readiness', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(console, 'log').mockImplementation(() => {});
    vi.spyOn(console, 'warn').mockImplementation(() => {});
  });

  it('lets the vendor confirm a made-to-order item is ready and shows the persisted state', async () => {
    mocks.getVendorOrder.mockResolvedValue(
      order([
        item({ id: 'item-mto', product_title: 'MTO Kaftan', made_to_order: true, readiness_state: 'being_prepared' }),
        item({ id: 'item-rtw', product_title: 'Ready Tee' }),
      ])
    );
    mocks.markVendorOrderItemReadyForPickup.mockResolvedValue({
      order_id: 'order-1',
      order_item_id: 'item-mto',
      already_ready: false,
      pickup: null,
      made_to_order: true,
      ready_for_pickup_at: '2026-10-04T09:30:00Z',
      readiness_state: 'ready_for_pickup',
    });

    renderPage();
    const panel = await screen.findByTestId('mto-panel-item-mto');
    expect(within(panel).getByText('Being prepared')).toBeInTheDocument();
    // Ready-to-wear items get the RTW readiness panel.
    expect(screen.queryByTestId('mto-panel-item-rtw')).not.toBeInTheDocument();
    expect(screen.getByTestId('rtw-panel-item-rtw')).toBeInTheDocument();
    expect(within(panel).getByRole('button', { name: 'Ready for Shopsoma Pickup' })).toBeInTheDocument();

    fireEvent.click(within(panel).getByRole('button', { name: 'Ready for Shopsoma Pickup' }));
    // Confirmation step prevents accidental notifications.
    expect(mocks.markVendorOrderItemReadyForPickup).not.toHaveBeenCalled();
    fireEvent.click(within(panel).getByRole('button', { name: "Yes, it's ready" }));

    await waitFor(() => {
      expect(mocks.markVendorOrderItemReadyForPickup).toHaveBeenCalledTimes(1);
    });
    expect(mocks.markVendorOrderItemReadyForPickup).toHaveBeenCalledWith('order-1', 'item-mto');
    expect(await within(panel).findByText('Ready for pickup')).toBeInTheDocument();
    expect(within(panel).getByText(/Marked ready:/)).toBeInTheDocument();
    expect(within(panel).queryByRole('button', { name: 'Ready for Shopsoma Pickup' })).not.toBeInTheDocument();
    expect(mocks.success).toHaveBeenCalledWith(
      'Shopsoma has been notified that this item is ready for pickup.',
      'Ready for pickup'
    );
  });

  it('shows already-ready items without the action and blocks unpaid orders', async () => {
    mocks.getVendorOrder.mockResolvedValue(
      order(
        [
          item({
            id: 'item-ready',
            made_to_order: true,
            readiness_state: 'ready_for_pickup',
            ready_for_pickup_at: '2026-10-04T09:30:00Z',
          }),
          item({ id: 'item-waiting', made_to_order: true, readiness_state: 'being_prepared' }),
        ],
        'pending'
      )
    );

    renderPage();
    const ready = await screen.findByTestId('mto-panel-item-ready');
    expect(within(ready).getByText('Ready for pickup')).toBeInTheDocument();
    expect(within(ready).getByText(/Marked ready:/)).toBeInTheDocument();

    const waiting = screen.getByTestId('mto-panel-item-waiting');
    expect(within(waiting).queryByRole('button', { name: 'Ready for Shopsoma Pickup' })).not.toBeInTheDocument();
    expect(within(waiting).getByText(/once the order payment is confirmed/)).toBeInTheDocument();
  });

  it('surfaces backend rejection and keeps the item not ready', async () => {
    mocks.getVendorOrder.mockResolvedValue(
      order([item({ id: 'item-mto', made_to_order: true, readiness_state: 'being_prepared' })])
    );
    mocks.markVendorOrderItemReadyForPickup.mockRejectedValue({
      response: { data: { detail: "You don't have access to this order item" } },
    });

    renderPage();
    const panel = await screen.findByTestId('mto-panel-item-mto');
    fireEvent.click(within(panel).getByRole('button', { name: 'Ready for Shopsoma Pickup' }));
    fireEvent.click(within(panel).getByRole('button', { name: "Yes, it's ready" }));

    await waitFor(() => {
      expect(mocks.error).toHaveBeenCalledWith("You don't have access to this order item", 'Error');
    });
    expect(within(panel).getByText('Being prepared')).toBeInTheDocument();
  });

  it('allows vendor to mark item ready when payment_status is uppercase PAID', async () => {
    mocks.getVendorOrder.mockResolvedValue(
      order(
        [item({ id: 'item-mto', product_title: 'MTO Kaftan', made_to_order: true, readiness_state: 'being_prepared' })],
        'PAID'
      )
    );

    renderPage();
    const panel = await screen.findByTestId('mto-panel-item-mto');
    expect(within(panel).getByRole('button', { name: 'Ready for Shopsoma Pickup' })).toBeInTheDocument();
    expect(within(panel).queryByText(/once the order payment is confirmed/)).not.toBeInTheDocument();
  });

  it('lets the vendor confirm a ready-to-wear item is available and ready for pickup', async () => {
    mocks.getVendorOrder.mockResolvedValue(
      order([
        item({ id: 'item-rtw', product_title: 'Ready Silk Shirt', made_to_order: false }),
      ])
    );
    mocks.markVendorOrderItemReadyForPickup.mockResolvedValue({
      order_id: 'order-1',
      order_item_id: 'item-rtw',
      already_ready: false,
      pickup: null,
      made_to_order: false,
      ready_for_pickup_at: '2026-10-08T14:00:00Z',
      readiness_state: 'ready_for_pickup',
    });

    renderPage();
    const panel = await screen.findByTestId('rtw-panel-item-rtw');
    expect(within(panel).getByText('Confirmation needed')).toBeInTheDocument();
    expect(within(panel).getByRole('button', { name: 'Ready for Shopsoma Pickup' })).toBeInTheDocument();

    fireEvent.click(within(panel).getByRole('button', { name: 'Ready for Shopsoma Pickup' }));
    expect(mocks.markVendorOrderItemReadyForPickup).not.toHaveBeenCalled();
    fireEvent.click(within(panel).getByRole('button', { name: "Yes, it's ready" }));

    await waitFor(() => {
      expect(mocks.markVendorOrderItemReadyForPickup).toHaveBeenCalledTimes(1);
    });
    expect(mocks.markVendorOrderItemReadyForPickup).toHaveBeenCalledWith('order-1', 'item-rtw');
    expect(await within(panel).findByText('Available & Ready for pickup')).toBeInTheDocument();
    expect(within(panel).getByText(/Confirmed ready:/)).toBeInTheDocument();
    expect(within(panel).queryByRole('button', { name: 'Ready for Shopsoma Pickup' })).not.toBeInTheDocument();
    expect(mocks.success).toHaveBeenCalledWith(
      'Shopsoma has been notified that this item is ready for pickup.',
      'Ready for pickup'
    );
  });
});
