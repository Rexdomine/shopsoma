import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import ProfileOrders from './ProfileOrders';

const { getOrders, getOrder, mockNavigate, mockLogout } = vi.hoisted(() => ({
  getOrders: vi.fn(),
  getOrder: vi.fn(),
  mockNavigate: vi.fn(),
  mockLogout: vi.fn(),
}));

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

vi.mock('../../services/checkoutService', () => ({
  checkoutService: {
    getOrders,
    getOrder,
  },
}));

vi.mock('../../context/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 'user-1', email: 'customer@shopsoma.com', full_name: 'Customer Test', role: 'customer' },
    isAuthenticated: true,
    logout: mockLogout,
  }),
}));

vi.mock('../../store/preferenceStore', () => ({
  usePreferenceStore: (selector: (state: { currency: string }) => unknown) =>
    selector({ currency: 'NGN' }),
}));

vi.mock('../../store/currencyStore', () => ({
  useCurrencyStore: () => ({
    currentCurrency: 'NGN',
    setCurrency: vi.fn(),
    commerceFeatures: { usd_switching_enabled: true },
  }),
}));

vi.mock('../../store/cartStore', () => ({
  useCartStore: (selector: (state: { cart: { summary: { itemCount: number } } }) => unknown) =>
    selector({ cart: { summary: { itemCount: 0 } } }),
}));

vi.mock('../../components/shipping/CustomerShippingQuotes', () => ({
  default: () => <div data-testid="shipping-quotes" />,
}));

describe('ProfileOrders', () => {
  const mockOrderData = {
    id: 'order-123',
    order_number: 'SHP-20261007-91DE0AAD',
    customer_id: 'user-1',
    currency: 'NGN',
    subtotal: 50000,
    shipping_cost: 3000,
    tax_amount: 0,
    discount_amount: 0,
    total_amount: 53000,
    payment_status: 'paid',
    fulfillment_status: 'preparing_for_pickup',
    created_at: '2026-10-07T08:00:00Z',
    items: [
      {
        id: 'item-1',
        product_title: 'Silk Adire Kaftan',
        variant_name: 'Blue / M',
        quantity: 2,
        unit_price: 25000,
        subtotal: 50000,
        product_image_url: '/images/kaftan.jpg',
      },
    ],
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders loading state initially and then shows customer orders list with formatted statuses without underscores', async () => {
    getOrders.mockResolvedValueOnce({
      orders: [mockOrderData],
      total: 1,
      page: 1,
      page_size: 10,
    });

    render(
      <MemoryRouter>
        <ProfileOrders />
      </MemoryRouter>
    );

    expect(screen.getByText('Loading orders...')).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'My Orders' })).toBeInTheDocument();
    });

    expect(screen.getByText('SHP-20261007-91DE0AAD')).toBeInTheDocument();
    expect(screen.getByText('Paid')).toBeInTheDocument();
    // Verify no underscore in fulfillment status: "Preparing For Pickup" instead of "Preparing For_pickup"
    expect(screen.getByText('Preparing For Pickup')).toBeInTheDocument();
    expect(screen.queryByText('Preparing For_pickup')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'View Details' })).toBeInTheDocument();
  });

  it('opens order details modal when clicking View Details or table row', async () => {
    getOrders.mockResolvedValueOnce({
      orders: [mockOrderData],
      total: 1,
      page: 1,
      page_size: 10,
    });
    getOrder.mockResolvedValueOnce(mockOrderData);

    render(
      <MemoryRouter>
        <ProfileOrders />
      </MemoryRouter>
    );

    await screen.findByText('SHP-20261007-91DE0AAD');

    fireEvent.click(screen.getByRole('button', { name: 'View Details' }));

    await waitFor(() => {
      expect(getOrder).toHaveBeenCalledWith('order-123');
    });

    expect(screen.getByText('Order Details')).toBeInTheDocument();
    expect(screen.getByText('Silk Adire Kaftan')).toBeInTheDocument();
    expect(screen.getByText('Blue / M')).toBeInTheDocument();
    expect(screen.getByText('Qty: 2')).toBeInTheDocument();

    // Close modal
    fireEvent.click(screen.getAllByRole('button', { name: 'Close' })[0]);
    expect(screen.queryByText('Order Details')).not.toBeInTheDocument();
  });

  it('navigates to tracking page when Track Order is clicked in modal', async () => {
    getOrders.mockResolvedValueOnce({
      orders: [mockOrderData],
      total: 1,
      page: 1,
      page_size: 10,
    });
    getOrder.mockResolvedValueOnce(mockOrderData);

    render(
      <MemoryRouter>
        <ProfileOrders />
      </MemoryRouter>
    );

    await screen.findByText('SHP-20261007-91DE0AAD');
    fireEvent.click(screen.getByRole('button', { name: 'View Details' }));

    await screen.findByText('Order Details');
    fireEvent.click(screen.getByRole('button', { name: 'Track Order' }));

    expect(mockNavigate).toHaveBeenCalledWith('/track/order-123');
  });

  it('renders empty state when customer has no orders', async () => {
    getOrders.mockResolvedValueOnce({
      orders: [],
      total: 0,
      page: 1,
      page_size: 10,
    });

    render(
      <MemoryRouter>
        <ProfileOrders />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText('You currently have no order yet')).toBeInTheDocument();
    });

    const shopBtn = screen.getByRole('button', { name: 'Go to Shop' });
    fireEvent.click(shopBtn);
    expect(mockNavigate).toHaveBeenCalledWith('/');
  });

  it('shows error banner with retry option when request fails', async () => {
    getOrders.mockRejectedValueOnce(new Error('Network error'));

    render(
      <MemoryRouter>
        <ProfileOrders />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText('Failed to load your orders. Please try again.')).toBeInTheDocument();
    });

    getOrders.mockResolvedValueOnce({
      orders: [mockOrderData],
      total: 1,
      page: 1,
      page_size: 10,
    });

    fireEvent.click(screen.getByRole('button', { name: 'Try Again' }));

    await waitFor(() => {
      expect(screen.getByText('SHP-20261007-91DE0AAD')).toBeInTheDocument();
    });
  });
});
