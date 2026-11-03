import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { STORAGE_KEYS } from '../../config/constants';
import OrderTracking from './OrderTracking';

const { getOrderTracking, getOrder, routeParams } = vi.hoisted(() => ({
  getOrderTracking: vi.fn(),
  getOrder: vi.fn(),
  routeParams: { orderId: 'order-1' },
}));

vi.mock('react-router-dom', () => ({
  Link: ({
    children,
    to,
    ...props
  }: {
    children: React.ReactNode;
    to?: string;
    state?: unknown;
  }) => (
    <a href={to} {...props}>
      {children}
    </a>
  ),
  useNavigate: () => vi.fn(),
  useParams: () => routeParams,
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
    routeParams.orderId = 'order-1';
    const storage = { clear: vi.fn(), getItem: vi.fn(() => null), setItem: vi.fn(), removeItem: vi.fn() };
    Object.defineProperty(window, 'localStorage', { configurable: true, value: storage });
    Object.defineProperty(window, 'sessionStorage', { configurable: true, value: storage });
    getOrderTracking.mockReset();
    getOrder.mockReset();
    getOrderTracking.mockRejectedValue({ response: { status: 404 } });
  });

  it('shows a not-logged-in message and login button without fabricated tracking data when unauthenticated', async () => {
    render(<OrderTracking />);

    const statusRegion = await screen.findByRole('status');
    expect(statusRegion).toHaveTextContent('You are not logged in');
    expect(statusRegion).toHaveTextContent(
      'Please log in to your account to view tracking information for this order.',
    );
    const loginLink = screen.getByRole('link', { name: /log in/i });
    expect(loginLink).toHaveAttribute('href', '/login');
    expect(screen.queryByText(/85,000|latest available information/i)).not.toBeInTheDocument();
    expect(
      screen.queryByText('Tracking information is unavailable. Please try again later.'),
    ).not.toBeInTheDocument();
    await waitFor(() => expect(getOrderTracking).toHaveBeenCalledWith('order-1', undefined));
  });

  it('shows order not found on your account message and switch account button when an authenticated user does not own the order', async () => {
    const storage = {
      clear: vi.fn(),
      getItem: vi.fn((key: string) =>
        key === STORAGE_KEYS.ACCESS_TOKEN ? 'valid-jwt-token' : null,
      ),
      setItem: vi.fn(),
      removeItem: vi.fn(),
    };
    Object.defineProperty(window, 'localStorage', { configurable: true, value: storage });

    render(<OrderTracking />);

    const statusRegion = await screen.findByRole('status');
    expect(statusRegion).toHaveTextContent('Order not found on your account');
    expect(statusRegion).toHaveTextContent(
      'This order does not belong to the account you are currently logged in with, or could not be found. Please log in with the account used to place this order.',
    );
    expect(
      screen.getByRole('link', { name: /log in with another account/i }),
    ).toHaveAttribute('href', '/login');
    expect(screen.getByRole('link', { name: /view my orders/i })).toHaveAttribute(
      'href',
      '/orders',
    );
    expect(
      screen.queryByText('Tracking information is unavailable. Please try again later.'),
    ).not.toBeInTheDocument();
  });

  it('clears previously loaded tracking and prompts login when a guest poll loses authorization', async () => {
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

    expect(await screen.findByText('You are not logged in')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /log in/i })).toHaveAttribute('href', '/login');
    expect(screen.queryByText('In Transit')).not.toBeInTheDocument();
  }, 15000);

  it('ignores a stale polling failure after a later poll recovers tracking', async () => {
    vi.useFakeTimers();
    try {
      let rejectFirstPoll: ((reason: unknown) => void) | undefined;
      const firstPoll = new Promise((_, reject) => {
        rejectFirstPoll = reject;
      });
      const recoveredTracking = {
        order_id: '550e8400-e29b-41d4-a716-446655440000',
        order_number: 'SHP-20260915-D791820A',
        tracking_id: 'TRACK-1',
        updated_at: '2026-01-01T00:00:00Z',
        currency: 'NGN',
        amount: 100,
        current_status: 'in_transit',
        history: [],
      };
      const initialTracking = {
        order_id: '550e8400-e29b-41d4-a716-446655440000',
        order_number: 'SHP-20260915-D791820A',
        tracking_id: 'TRACK-1',
        updated_at: '2026-01-01T00:00:00Z',
        currency: 'NGN',
        amount: 100,
        current_status: 'in_transit',
        history: [],
      };
      getOrderTracking
        .mockResolvedValueOnce(initialTracking)
        .mockReturnValueOnce(firstPoll)
        .mockResolvedValue(recoveredTracking);

      render(<OrderTracking />);
      await act(async () => {
        await Promise.resolve();
      });

      await act(async () => {
        await vi.advanceTimersByTimeAsync(20000);
      });
      expect(screen.getAllByText('In Transit').length).toBeGreaterThan(0);

      await act(async () => {
        rejectFirstPoll?.({ response: { status: 404 } });
        await Promise.resolve();
      });

      expect(screen.getAllByText('In Transit').length).toBeGreaterThan(0);
      expect(screen.queryByText('Tracking information is unavailable. Please try again later.')).not.toBeInTheDocument();
      expect(screen.queryByText('You are not logged in')).not.toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it('accepts a slow poll after a newer poll has started but not settled', async () => {
    vi.useFakeTimers();
    try {
      let resolveFirstPoll: ((value: unknown) => void) | undefined;
      const firstPoll = new Promise((resolve) => {
        resolveFirstPoll = resolve;
      });
      const secondPoll = new Promise(() => {});
      const initialTracking = {
        order_id: 'order-1',
        order_number: 'SHP-20260915-D791820A',
        tracking_id: 'TRACK-1',
        updated_at: '2026-01-01T00:00:00Z',
        currency: 'NGN',
        amount: 100,
        current_status: 'in_transit',
        history: [],
      };
      getOrderTracking
        .mockResolvedValueOnce(initialTracking)
        .mockReturnValueOnce(firstPoll)
        .mockReturnValueOnce(secondPoll);

      render(<OrderTracking />);
      await act(async () => {
        await Promise.resolve();
      });

      await act(async () => {
        await vi.advanceTimersByTimeAsync(20000);
      });
      expect(getOrderTracking).toHaveBeenCalledTimes(3);

      await act(async () => {
        resolveFirstPoll?.({
          ...initialTracking,
          current_status: 'delivered',
          updated_at: '2026-01-01T00:01:00Z',
        });
        await Promise.resolve();
      });

      expect(screen.getAllByText('Delivered').length).toBeGreaterThan(0);
      expect(screen.queryByText('Tracking information is unavailable. Please try again later.')).not.toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

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

  it('passes the order number to tracking recovery', async () => {
    routeParams.orderId = 'SHP-20260915-D791820A';
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

    render(<OrderTracking />);

    await waitFor(() =>
      expect(getOrderTracking).toHaveBeenCalledWith('SHP-20260915-D791820A', undefined),
    );
  });
});
