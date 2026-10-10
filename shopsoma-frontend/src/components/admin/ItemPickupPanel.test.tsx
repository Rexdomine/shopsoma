import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  updatePickupStatus: vi.fn(),
  adminMarkItemReady: vi.fn(),
}));

vi.mock('../../services/adminOrderService', () => ({
  updatePickupStatus: mocks.updatePickupStatus,
  adminMarkItemReady: mocks.adminMarkItemReady,
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
    expect(screen.getByTestId('mark-ready-item-a')).toBeInTheDocument();
  });

  it('allows admin to mark an unready made-to-order item ready', async () => {
    const updatedOrder = { id: 'order-1' } as OrderDetail;
    mocks.adminMarkItemReady.mockResolvedValue(updatedOrder);
    const props = renderPanel(mtoItem());

    const markReadyBtn = screen.getByTestId('mark-ready-item-a');
    expect(markReadyBtn).toHaveTextContent('Mark Ready (Admin)');
    fireEvent.click(markReadyBtn);

    await waitFor(() => {
      expect(mocks.adminMarkItemReady).toHaveBeenCalledWith('order-1', 'item-a');
    });
    expect(props.onUpdated).toHaveBeenCalledWith(updatedOrder);
    expect(props.onSuccess).toHaveBeenCalledWith(expect.stringContaining('as ready for pickup'));
  });

  it('renders and schedules pickup for a ready ready-to-wear (RTW) item', async () => {
    const updatedOrder = { id: 'order-1' } as OrderDetail;
    mocks.updatePickupStatus.mockResolvedValue(updatedOrder);
    const rtwItem: OrderItemDetail = {
      ...mtoItem(),
      id: 'rtw-item-1',
      made_to_order: false,
      readiness_state: 'ready_for_pickup',
      ready_for_pickup_at: '2026-10-10T12:00:00Z',
      pickup: { id: 'pickup-rtw-1', order_item_id: 'rtw-item-1', vendor_id: 'vendor-a', status: 'pending' },
    };

    const props = renderPanel(rtwItem);

    expect(screen.getByText('Individual Pickup:')).toBeInTheDocument();
    expect(screen.getByText('Ready for pickup')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Schedule pickup' })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Schedule pickup' }));
    fireEvent.change(screen.getByLabelText(/Pickup window start/), { target: { value: '2026-10-11T10:00' } });
    fireEvent.change(screen.getByLabelText(/Pickup window end/), { target: { value: '2026-10-11T12:00' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save pickup' }));

    await waitFor(() => {
      expect(mocks.updatePickupStatus).toHaveBeenCalledWith(
        'order-1',
        'pickup-rtw-1',
        expect.objectContaining({
          pickup_window_start: new Date('2026-10-11T10:00').toISOString(),
          pickup_window_end: new Date('2026-10-11T12:00').toISOString(),
        })
      );
    });
    expect(props.onUpdated).toHaveBeenCalledWith(updatedOrder);
  });

  it('allows admin to mark ready an unconfirmed RTW item', async () => {
    const updatedOrder = { id: 'order-1' } as OrderDetail;
    mocks.adminMarkItemReady.mockResolvedValue(updatedOrder);
    const unconfirmedRtwItem: OrderItemDetail = {
      ...mtoItem(),
      id: 'rtw-item-2',
      made_to_order: false,
      readiness_state: 'pending_confirmation',
      ready_for_pickup_at: null,
      pickup: { id: 'pickup-rtw-2', order_item_id: 'rtw-item-2', vendor_id: 'vendor-a', status: 'pending' },
    };

    const props = renderPanel(unconfirmedRtwItem);

    expect(screen.getByText('Awaiting vendor confirmation')).toBeInTheDocument();
    const markReadyBtn = screen.getByTestId('mark-ready-rtw-item-2');
    fireEvent.click(markReadyBtn);

    await waitFor(() => {
      expect(mocks.adminMarkItemReady).toHaveBeenCalledWith('order-1', 'rtw-item-2');
    });
    expect(props.onUpdated).toHaveBeenCalledWith(updatedOrder);
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

  it('renders configured production duration and working days countdown for in-progress MTO item', () => {
    renderPanel(
      mtoItem({
        production_duration: '5-7 business days',
        estimated_production_days: 7,
        working_days_left: 4,
        production_due_date: '2026-10-15T12:00:00Z',
      })
    );

    expect(screen.getByTestId('mto-duration')).toHaveTextContent('Duration: 5-7 business days');
    expect(screen.getByTestId('mto-countdown')).toHaveTextContent('4 working days left');
    expect(screen.getByText(/Estimated completion:/)).toBeInTheDocument();
  });

  it('renders overdue status when working days left is negative', () => {
    renderPanel(
      mtoItem({
        production_duration: '3 working days',
        working_days_left: -2,
        is_production_overdue: true,
      })
    );

    expect(screen.getByTestId('mto-duration')).toHaveTextContent('Duration: 3 working days');
    expect(screen.getByTestId('mto-countdown')).toHaveTextContent('Overdue by 2 working days');
  });

  it('handles missing timeline and unconfigured duration safely', () => {
    renderPanel(
      mtoItem({
        production_duration: null,
        estimated_production_days: null,
        working_days_left: null,
      })
    );

    expect(screen.getByTestId('mto-duration')).toHaveTextContent('Duration: Not specified');
    expect(screen.getByTestId('mto-countdown')).toHaveTextContent('Timeline not configured');
  });

  it('shows production completed once marked ready regardless of remaining days', () => {
    renderPanel(
      mtoItem({
        production_duration: '5 working days',
        working_days_left: 3,
        readiness_state: 'ready_for_pickup',
        ready_for_pickup_at: '2026-10-06T10:00:00Z',
        is_production_completed: true,
      })
    );

    expect(screen.getByTestId('mto-duration')).toHaveTextContent('Duration: 5 working days');
    expect(screen.getByTestId('mto-countdown')).toHaveTextContent('Production completed');
    expect(screen.queryByText(/Estimated completion:/)).not.toBeInTheDocument();
  });
});

