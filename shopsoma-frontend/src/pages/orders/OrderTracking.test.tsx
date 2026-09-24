import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import OrderTracking from './OrderTracking';

const { getOrderTracking, getOrder } = vi.hoisted(() => ({
  getOrderTracking: vi.fn(),
  getOrder: vi.fn(),
}));

vi.mock('react-router-dom', () => ({
  Link: ({ children, ...props }: { children: React.ReactNode }) => <a {...props}>{children}</a>,
  useNavigate: () => vi.fn(),
  useParams: () => ({ orderId: 'order-1' }),
}));

vi.mock('../../services/orderService', () => ({
  orderService: { getOrderTracking },
}));

vi.mock('../../services/checkoutService', () => ({
  checkoutService: { getOrder },
}));

vi.mock('../../../services/websocketService', () => ({
  default: { isConnected: () => false, connect: vi.fn(), disconnect: vi.fn() },
}));

vi.mock('../../store/currencyStore', () => ({
  useCurrencyStore: (selector: (state: { exchangeRates: Record<string, number> }) => unknown) =>
    selector({ exchangeRates: {} }),
}));

vi.mock('../../utils/pricing', () => ({
  formatPriceWithConversion: (amount: number) => String(amount),
}));

vi.mock('../../utils/checkoutCapability', () => ({
  loadCheckoutCapability: () => undefined,
}));

describe('OrderTracking', () => {
  beforeEach(() => {
    const storage = { clear: vi.fn(), getItem: vi.fn(() => null), setItem: vi.fn(), removeItem: vi.fn() };
    Object.defineProperty(window, 'localStorage', { configurable: true, value: storage });
    Object.defineProperty(window, 'sessionStorage', { configurable: true, value: storage });
    getOrderTracking.mockReset();
    getOrder.mockReset();
    getOrderTracking.mockRejectedValue({ response: { status: 404 } });
  });

  it('does not show fabricated tracking data when guest read access expires', async () => {
    render(<OrderTracking />);

    expect(await screen.findByRole('status')).toHaveTextContent(
      'Tracking information is unavailable for this order.',
    );
    expect(screen.queryByText(/85,000|latest available information/i)).not.toBeInTheDocument();
    await waitFor(() => expect(getOrderTracking).toHaveBeenCalledWith('order-1', undefined));
  });

  it('clears previously loaded tracking when a protected poll loses authorization', async () => {
    getOrderTracking
      .mockResolvedValueOnce({
        current_status: 'in_transit',
        tracking_number: 'TRACK-1',
        updated_at: '2026-01-01T00:00:00Z',
        delivery_provider: 'manual',
        currency: 'NGN',
        amount: 100,
        history: [],
      })
      .mockRejectedValueOnce({ response: { status: 404 } });
    render(<OrderTracking />);
    await waitFor(() => expect(screen.getAllByText('In Transit').length).toBeGreaterThan(0));

    await new Promise((resolve) => setTimeout(resolve, 10050));

    expect(await screen.findByText('Tracking information is unavailable. Please try again later.')).toBeInTheDocument();
    expect(screen.queryByText('In Transit')).not.toBeInTheDocument();
  }, 15000);

  it('uses the resolved UUID for order details after tracking by order number', async () => {
    getOrderTracking.mockResolvedValue({
      order_id: '550e8400-e29b-41d4-a716-446655440000',
      order_number: 'SHP-20260915-D791820A',
      tracking_id: 'TRACK-1',
      updated_at: '2026-01-01T00:00:00Z',
      currency: 'NGN',
      amount: 100,
      current_status: 'in_transit',
      history: [],
    });
    getOrder.mockResolvedValue({});

    render(<OrderTracking />);
    const orderButton = await screen.findByRole('button', { name: 'SHP-20260915-D791820A' });
    fireEvent.click(orderButton);

    await waitFor(() =>
      expect(getOrder).toHaveBeenCalledWith(
        '550e8400-e29b-41d4-a716-446655440000',
        undefined,
      ),
    );
  });

  it('recovers order-number tracking after a transient initial failure', async () => {
    vi.useFakeTimers();
    try {
      getOrderTracking
        .mockRejectedValueOnce({ response: { status: 503 } })
        .mockResolvedValueOnce({
          order_id: '550e8400-e29b-41d4-a716-446655440000',
          order_number: 'SHP-20260915-D791820A',
          tracking_id: 'TRACK-1',
          updated_at: '2026-01-01T00:00:00Z',
          currency: 'NGN',
          amount: 100,
          current_status: 'in_transit',
          history: [],
        });

      render(<OrderTracking />);
      await act(async () => {
        await Promise.resolve();
      });
      expect(screen.getByText('Tracking information is unavailable. Please try again later.')).toBeInTheDocument();

      await act(async () => {
        await vi.advanceTimersByTimeAsync(10000);
      });

      expect(screen.getAllByText('In Transit').length).toBeGreaterThan(0);
      expect(screen.queryByText('Tracking information is unavailable. Please try again later.')).not.toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });
});
