import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  updatePickupStatus: vi.fn(),
}));

vi.mock('../../services/adminOrderService', () => ({
  updatePickupStatus: mocks.updatePickupStatus,
}));

import ItemPickupPanel from './ItemPickupPanel';
import type { OrderDetail, OrderItemDetail } from '../../services/adminOrderService';

const mtoItem = (overrides: Partial<OrderItemDetail> = {}): OrderItemDetail => ({
  id: 'item-a',
  product_id: 'product-a',
  product_title: 'Made-to-order Trousers',
  variant_details: {},
  unit_price: 1000,
  currency: 'NGN',
  quantity: 1,
  subtotal: 1000,
  commission_rate: 0,
  commission_amount: 0,
  vendor_payout: 1000,
  fulfillment_status: 'order_received',
  vendor: { id: 'vendor-a', business_name: 'Vendor A' },
  made_to_order: true,
  ready_for_pickup_at: null,
  readiness_state: 'being_prepared',
  pickup: { id: 'pickup-a', order_item_id: 'item-a', vendor_id: 'vendor-a', status: 'scheduled' },
  ...overrides,
});

const renderPanel = (item: OrderItemDetail) => {
  const props = {
    onUpdated: vi.fn(),
    onSuccess: vi.fn(),
    onError: vi.fn(),
  };
  render(<ItemPickupPanel orderId="order-1" item={item} {...props} />);
  return props;
};

describe('ItemPickupPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows "not ready" and offers no scheduling for an unready made-to-order item', () => {
    renderPanel(mtoItem());

    expect(screen.getByText('Made to order')).toBeInTheDocument();
    expect(screen.getByText('Not ready yet')).toBeInTheDocument();
    expect(screen.getByText(/Waiting for Vendor A to mark this item ready/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Schedule pickup' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Mark picked up' })).not.toBeInTheDocument();
  });

  it('schedules a pickup for a ready item through the per-item pickup endpoint', async () => {
    const updatedOrder = { id: 'order-1' } as OrderDetail;
    mocks.updatePickupStatus.mockResolvedValue(updatedOrder);
    const props = renderPanel(
      mtoItem({ readiness_state: 'ready_for_pickup', ready_for_pickup_at: '2026-10-04T09:30:00Z' })
    );

    expect(screen.getByText('Ready for pickup')).toBeInTheDocument();
    expect(screen.getByText(/Marked ready:/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Schedule pickup' }));
    fireEvent.change(screen.getByLabelText(/Pickup window start/), { target: { value: '2026-10-05T10:00' } });
    fireEvent.change(screen.getByLabelText(/Pickup window end/), { target: { value: '2026-10-05T12:00' } });
    fireEvent.change(screen.getByLabelText('Courier name'), { target: { value: 'Shopsoma Rider' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save pickup' }));

    await waitFor(() => {
      expect(mocks.updatePickupStatus).toHaveBeenCalledWith('order-1', 'pickup-a', {
        pickup_window_start: new Date('2026-10-05T10:00').toISOString(),
        pickup_window_end: new Date('2026-10-05T12:00').toISOString(),
        courier_name: 'Shopsoma Rider',
        rider_id: undefined,
        logistics_partner: undefined,
        tracking_number: undefined,
        admin_notes: undefined,
      });
    });
    expect(props.onUpdated).toHaveBeenCalledWith(updatedOrder);
    expect(props.onSuccess).toHaveBeenCalledWith(expect.stringContaining('Vendor A'));
  });

  it('rejects an inverted pickup window without calling the API', () => {
    const props = renderPanel(mtoItem({ readiness_state: 'ready_for_pickup', ready_for_pickup_at: '2026-10-04T09:30:00Z' }));

    fireEvent.click(screen.getByRole('button', { name: 'Schedule pickup' }));
    fireEvent.change(screen.getByLabelText(/Pickup window start/), { target: { value: '2026-10-05T12:00' } });
    fireEvent.change(screen.getByLabelText(/Pickup window end/), { target: { value: '2026-10-05T10:00' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save pickup' }));

    expect(mocks.updatePickupStatus).not.toHaveBeenCalled();
    expect(props.onError).toHaveBeenCalledWith('Pickup window end must be after the start');
  });

  it('marks a scheduled item as picked up and surfaces backend errors', async () => {
    mocks.updatePickupStatus.mockRejectedValueOnce({ response: { data: { detail: 'Backend says no' } } });
    const props = renderPanel(
      mtoItem({
        readiness_state: 'pickup_scheduled',
        ready_for_pickup_at: '2026-10-04T09:30:00Z',
        pickup: {
          id: 'pickup-a',
          status: 'scheduled',
          pickup_window_start: '2026-10-05T10:00:00Z',
          pickup_window_end: '2026-10-05T12:00:00Z',
        },
      })
    );

    expect(screen.getByText('Pickup scheduled')).toBeInTheDocument();
    expect(screen.getByText(/Pickup window:/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Mark picked up' }));

    await waitFor(() => {
      expect(mocks.updatePickupStatus).toHaveBeenCalledWith('order-1', 'pickup-a', { pickup_status: 'in_transit' });
    });
    await waitFor(() => expect(props.onError).toHaveBeenCalledWith('Backend says no'));
    expect(within(screen.getByTestId('item-pickup-panel-item-a')).getByRole('button', { name: 'Edit pickup' })).toBeInTheDocument();
  });
});
