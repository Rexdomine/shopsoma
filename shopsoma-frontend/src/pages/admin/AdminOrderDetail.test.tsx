import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  getOrderDetail: vi.fn(),
  runShadowQuote: vi.fn(),
  createDhlBooking: vi.fn(),
  getDhlLabel: vi.fn(),
  recordDhlHandoff: vi.fn(),
  refreshDhlTracking: vi.fn(),
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
  createDhlBooking: mocks.createDhlBooking,
  getDhlLabel: mocks.getDhlLabel,
  recordDhlHandoff: mocks.recordDhlHandoff,
  refreshDhlTracking: mocks.refreshDhlTracking,
}));

import AdminOrderDetail from './AdminOrderDetail';
import DhlShipmentOperations from '../../components/admin/DhlShipmentOperations';
import type { OrderDetail, ShadowQuoteResult, DhlOperationBooking } from '../../services/adminOrderService';

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


describe('AdminOrderDetail DHL shipment operations', () => {
  it('shows the shipment operations panel and states that DHL pickup booking is unavailable', async () => {
    mocks.getOrderDetail.mockResolvedValue(baseOrder());
    renderPage();
    await screen.findByText('Order #1001');
    expect(screen.getByRole('heading', { name: 'DHL Shipment Operations' })).toBeInTheDocument();
    expect(screen.getByText(/DHL pickup booking is unavailable/i)).toBeInTheDocument();
    expect(screen.getByText(/Shipment operations are unavailable until backend shipment facts can be loaded/)).toBeInTheDocument();
  });
});


function operationsOrder(count = 1): OrderDetail {
  return { ...baseOrder(), dhl_operations: {
    read_at: '2026-09-28T10:00:00Z', bookings: [],
    packages: Array.from({ length: count }, (_, n) => ({
      package_id: `package-${n}`, package_version: n + 3, origin_hub_id: 'hub-1',
      package_state: 'ready', ready_at: '2026-09-28T09:00:00Z', seal_id: `seal-${n}`,
      intent_id: `intent-${n}`, active_booking_id: null, selection_eligible: true, selection_blockers: [],
    })),
  } };
}

function recordedBooking(): DhlOperationBooking {
  return { booking_id: 'booking-1', intent_id: 'intent-0', package_id: 'package-0', package_version: 3,
    seal_id: 'seal-0', origin_hub_id: 'hub-1', created_at: '2026-09-28T10:00:00Z',
    classification: 'success', outbound_state: 'booked', tracking_number: 'test-tracking',
    label_available: true, handoff_recorded_at: null, last_tracking_refresh_at: null,
    reconciliation_state: 'not_required', reconciliation_resolution: null, reconciliation_recorded_at: null };
}

describe('AdminOrderDetail DHL mutation safety', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    mocks.getOrderDetail.mockResolvedValue(operationsOrder());
  });

  it('requires explicit multi-package selection and confirmation and sends exact facts once', async () => {
    const order = operationsOrder(2);
    mocks.getOrderDetail.mockResolvedValue(order);
    mocks.createDhlBooking.mockReturnValue(new Promise(() => {}));
    renderPage();
    const create = await screen.findByRole('button', { name: 'Create DHL shipment' });
    expect(create).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Ready hub package'), { target: { value: 'package-1' } });
    fireEvent.click(create);
    expect(mocks.createDhlBooking).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(mocks.createDhlBooking).not.toHaveBeenCalled();
    fireEvent.click(create);
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: /^(Create DHL shipment|Record DHL handoff|Refresh DHL tracking)$/ }));
    fireEvent.click(create);
    expect(mocks.createDhlBooking).toHaveBeenCalledTimes(1);
    expect(mocks.createDhlBooking).toHaveBeenCalledWith('order-1', {
      intent_id: 'intent-1', package_id: 'package-1', package_version: 4, seal_id: 'seal-1',
      idempotency_key: expect.any(String),
    });
    expect(localStorage.getItem('shopsoma:dhl:unresolved:order-1')).toBe('1');
  });

  it('keeps a timed-out booking blocked after reload even when GET has no attempt and hides raw errors', async () => {
    mocks.createDhlBooking.mockRejectedValue(new Error('PRIVATE PROVIDER PAYLOAD'));
    const first = renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Create DHL shipment' }));
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: /^(Create DHL shipment|Record DHL handoff|Refresh DHL tracking)$/ }));
    await screen.findByText(/Operation could not be confirmed/);
    expect(screen.queryByText(/PRIVATE PROVIDER/)).not.toBeInTheDocument();
    first.unmount(); renderPage();
    expect(await screen.findByRole('button', { name: 'Create DHL shipment' })).toBeDisabled();
    expect(mocks.createDhlBooking).toHaveBeenCalledTimes(1);
  });

  it('keeps recorded unknown outcomes unavailable across administrators without local storage', async () => {
    const order = operationsOrder();
    order.dhl_operations!.packages[0].selection_eligible = false;
    order.dhl_operations!.packages[0].selection_blockers = ['reconciliation_required'];
    order.dhl_operations!.bookings = [{ ...recordedBooking(), classification: 'unknown', reconciliation_state: 'required' }];
    mocks.getOrderDetail.mockResolvedValue(order);
    renderPage();
    expect(await screen.findByRole('button', { name: 'Create DHL shipment' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Refresh DHL tracking' })).toBeDisabled();
    expect(screen.getByText(/This attempt requires review/)).toBeInTheDocument();
  });

  it('preserves booking history when no ready packages remain and refreshes tracking only after confirmation', async () => {
    const order = operationsOrder(0);
    order.dhl_operations!.bookings = [recordedBooking()];
    mocks.getOrderDetail.mockResolvedValue(order);
    mocks.refreshDhlTracking.mockResolvedValue({});
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Refresh DHL tracking' }));
    expect(mocks.refreshDhlTracking).not.toHaveBeenCalled();
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: /^(Create DHL shipment|Record DHL handoff|Refresh DHL tracking)$/ }));
    await screen.findByText('DHL tracking refreshed.');
    expect(mocks.refreshDhlTracking).toHaveBeenCalledWith('order-1', { booking_id: 'booking-1', idempotency_key: expect.any(String) });
    expect(localStorage.length).toBe(0);
  });

  it('uses the protected binary label service for historical bookings', async () => {
    const order = operationsOrder(0);
    order.dhl_operations!.bookings = [recordedBooking()];
    mocks.getOrderDetail.mockResolvedValue(order);
    mocks.getDhlLabel.mockResolvedValue(new Blob(['pdf'], { type: 'application/pdf' }));
    URL.createObjectURL = vi.fn(() => 'blob:test'); URL.revokeObjectURL = vi.fn();
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Download DHL label' }));
    await screen.findByText('DHL label downloaded.');
    expect(mocks.getDhlLabel).toHaveBeenCalledWith('order-1', 'booking-1');
    click.mockRestore();
  });

  it('validates private evidence references and records confirmed handoff without persisting evidence', async () => {
    const order = operationsOrder(0);
    order.dhl_operations!.bookings = [recordedBooking()];
    mocks.getOrderDetail.mockResolvedValue(order);
    mocks.recordDhlHandoff.mockResolvedValue({});
    renderPage();
    await screen.findByRole('button', { name: 'Record DHL handoff' });
    fireEvent.change(screen.getByLabelText(/Collection time/), { target: { value: '2026-09-28T10:00' } });
    fireEvent.change(screen.getByLabelText('Counterparty'), { target: { value: 'DHL collection' } });
    fireEvent.change(screen.getByLabelText('Private evidence reference'), { target: { value: 'https://private.test/evidence' } });
    fireEvent.change(screen.getByLabelText('Evidence SHA-256'), { target: { value: 'a'.repeat(64) } });
    fireEvent.click(screen.getByRole('button', { name: 'Record DHL handoff' }));
    expect(mocks.recordDhlHandoff).not.toHaveBeenCalled();
    expect(screen.getByText(/URLs and absolute paths are not accepted/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Private evidence reference'), { target: { value: 'custody/evidence-1' } });
    fireEvent.click(screen.getByRole('button', { name: 'Record DHL handoff' }));
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: /^(Create DHL shipment|Record DHL handoff|Refresh DHL tracking)$/ }));
    await screen.findByText('Hub-to-DHL handoff recorded.');
    expect(mocks.recordDhlHandoff).toHaveBeenCalledWith('order-1', 'booking-1', {
      occurred_at: new Date('2026-09-28T10:00').toISOString(), counterparty: 'DHL collection',
      evidence_ref: 'custody/evidence-1', evidence_sha256: 'a'.repeat(64), idempotency_key: expect.any(String),
    });
    expect(localStorage.length).toBe(0);
  });

  it('clears the command lock only after confirmed booking is visible in backend history', async () => {
    const fresh = operationsOrder();
    fresh.dhl_operations!.bookings = [recordedBooking()];
    fresh.dhl_operations!.packages[0].selection_eligible = false;
    fresh.dhl_operations!.packages[0].selection_blockers = ['active_booking_exists'];
    mocks.getOrderDetail.mockResolvedValueOnce(operationsOrder()).mockResolvedValue(fresh);
    mocks.createDhlBooking.mockResolvedValue({ booking_id: 'booking-1', result_kind: 'booked' });
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Create DHL shipment' }));
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: /^(Create DHL shipment|Record DHL handoff|Refresh DHL tracking)$/ }));
    await screen.findByText(/DHL shipment created/);
    expect(localStorage.length).toBe(0);
    expect(screen.getByRole('button', { name: 'Create DHL shipment' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Download DHL label' })).toBeEnabled();
  });

  it('never sends a mutation if its reload safety marker cannot be persisted', async () => {
    const storage = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('quota'); });
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Create DHL shipment' }));
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: /^(Create DHL shipment|Record DHL handoff|Refresh DHL tracking)$/ }));
    await screen.findByText(/Operation could not be confirmed/);
    expect(mocks.createDhlBooking).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'Create DHL shipment' })).toBeDisabled();
    storage.mockRestore();
  });

  it('blocks cancelled-order mutations but preserves authorized label access', async () => {
    const order = operationsOrder(); order.fulfillment_status = 'cancelled';
    order.dhl_operations!.bookings = [recordedBooking()];
    mocks.getOrderDetail.mockResolvedValue(order);
    renderPage();
    expect(await screen.findByRole('button', { name: 'Create DHL shipment' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Refresh DHL tracking' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Record DHL handoff' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Download DHL label' })).toBeEnabled();
  });

});

describe('DHL correction regressions', () => {
  beforeEach(() => { vi.clearAllMocks(); localStorage.clear(); });
  const fill = (suffix: string) => {
    fireEvent.change(screen.getByLabelText(/Collection time/), { target: { value: '2026-09-28T10:00' } });
    fireEvent.change(screen.getByLabelText('Counterparty'), { target: { value: 'Collector ' + suffix } });
    fireEvent.change(screen.getByLabelText('Private evidence reference'), { target: { value: 'custody/' + suffix } });
    fireEvent.change(screen.getByLabelText('Evidence SHA-256'), { target: { value: suffix.repeat(64) } });
  };
  it('isolates A/B drafts, rejects empty B submission and sends only B evidence', async () => {
    const order = operationsOrder();
    order.dhl_operations!.bookings = [recordedBooking(), { ...recordedBooking(), booking_id: 'booking-2' }];
    mocks.getOrderDetail.mockResolvedValue(order);
    mocks.recordDhlHandoff.mockResolvedValue({});
    renderPage();
    const selector = await screen.findByLabelText('Shipment record');
    fireEvent.change(selector, { target: { value: 'booking-1' } }); fill('a');
    fireEvent.change(selector, { target: { value: 'booking-2' } });
    for (const label of [/Collection time/, 'Counterparty', 'Private evidence reference', 'Evidence SHA-256']) {
      expect(screen.getByLabelText(label)).toHaveValue('');
    }
    fireEvent.submit(screen.getByRole('button', { name: 'Record DHL handoff' }).closest('form')!);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    fill('b');
    fireEvent.change(selector, { target: { value: 'booking-1' } });
    expect(screen.getByLabelText('Counterparty')).toHaveValue('Collector a');
    fireEvent.change(selector, { target: { value: 'booking-2' } });
    fireEvent.click(screen.getByRole('button', { name: 'Record DHL handoff' }));
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: /Confirm|Record DHL handoff/ }));
    await waitFor(() => expect(mocks.recordDhlHandoff).toHaveBeenCalledWith('order-1', 'booking-2', {
      occurred_at: new Date('2026-09-28T10:00').toISOString(), counterparty: 'Collector b',
      evidence_ref: 'custody/b', evidence_sha256: 'b'.repeat(64), idempotency_key: expect.any(String),
    }));
    await screen.findByText('Hub-to-DHL handoff recorded.');
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
  });

  it.each(['removed', 'recorded', 'ineligible'])('invalidates handoff confirmation when booking becomes %s', (change) => {
    const order = operationsOrder(); order.dhl_operations!.bookings = [recordedBooking()];
    const view = render(<DhlShipmentOperations order={order} onOrderChange={vi.fn()} />);
    fill('a'); fireEvent.click(screen.getByRole('button', { name: 'Record DHL handoff' }));
    const fresh = structuredClone(order);
    if (change === 'removed') fresh.dhl_operations!.bookings = [{ ...recordedBooking(), booking_id: 'booking-2' }];
    if (change === 'recorded') fresh.dhl_operations!.bookings[0].handoff_recorded_at = '2026-09-28T10:00:00Z';
    if (change === 'ineligible') fresh.dhl_operations!.bookings[0].reconciliation_state = 'required';
    view.rerender(<DhlShipmentOperations order={fresh} onOrderChange={vi.fn()} />);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.getByText(/Shipment records changed/)).toBeInTheDocument();
    expect(mocks.recordDhlHandoff).not.toHaveBeenCalled();
    expect(localStorage.length).toBe(0);
  });

  it.each(['Create DHL shipment', 'Record DHL handoff', 'Refresh DHL tracking'])('contains focus and restores %s on Escape/cancel', async (name) => {
    const order = operationsOrder(); order.dhl_operations!.bookings = [recordedBooking()];
    mocks.getOrderDetail.mockResolvedValue(order); renderPage();
    const trigger = await screen.findByRole('button', { name });
    if (name === 'Record DHL handoff') fill('a');
    trigger.focus(); fireEvent.click(trigger);
    const dialog = screen.getByRole('dialog');
    const cancel = within(dialog).getByRole('button', { name: 'Cancel' });
    const action = within(dialog).getByRole('button', { name: /Confirm|^Create DHL shipment$|^Record DHL handoff$|^Refresh DHL tracking$/ });
    expect(cancel).toHaveFocus();
    expect(trigger.closest('[inert]')).not.toBeNull();
    trigger.focus(); expect(cancel).toHaveFocus();
    fireEvent.keyDown(cancel, { key: 'Tab', shiftKey: true }); expect(action).toHaveFocus();
    fireEvent.keyDown(action, { key: 'Tab' }); expect(cancel).toHaveFocus();
    expect(trigger.closest('[inert]')).not.toBeNull();
    trigger.focus(); expect(cancel).toHaveFocus();
    fireEvent.keyDown(cancel, { key: 'Escape' });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument(); expect(trigger).toHaveFocus();
    fireEvent.click(trigger); fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Cancel' }));
    expect(trigger).toHaveFocus();
    expect(mocks.createDhlBooking).not.toHaveBeenCalled(); expect(mocks.recordDhlHandoff).not.toHaveBeenCalled();
  });
});
