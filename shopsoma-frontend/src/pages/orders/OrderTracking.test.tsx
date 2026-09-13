import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import OrderTracking from './OrderTracking';

const { getOrderTracking } = vi.hoisted(() => ({
  getOrderTracking: vi.fn(),
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
  checkoutService: { getOrder: vi.fn() },
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
});
