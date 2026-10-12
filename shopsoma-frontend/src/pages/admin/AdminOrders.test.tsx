import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import AdminOrders from './AdminOrders';
import type { OrderListItem, OrderStats } from '../../services/adminOrderService';

const mockNavigate = vi.fn();

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

const mocks = vi.hoisted(() => ({
  listOrders: vi.fn(),
  getOrderStats: vi.fn(),
  bulkUpdateStatus: vi.fn(),
  exportOrdersCSV: vi.fn(),
  downloadCSV: vi.fn(),
  toastSuccess: vi.fn(),
  toastError: vi.fn(),
  toastWarning: vi.fn(),
  hideToast: vi.fn(),
}));

vi.mock('../../services/adminOrderService', () => ({
  listOrders: mocks.listOrders,
  getOrderStats: mocks.getOrderStats,
  bulkUpdateStatus: mocks.bulkUpdateStatus,
  exportOrdersCSV: mocks.exportOrdersCSV,
  downloadCSV: mocks.downloadCSV,
}));

vi.mock('../../components/admin/AdminSidebar', () => ({
  default: ({ activeSection }: { activeSection: string }) => (
    <aside data-testid="admin-sidebar" data-active-section={activeSection} />
  ),
}));

vi.mock('../../components/common/CurrencySwitcher', () => ({
  default: () => <div data-testid="currency-switcher" />,
}));

vi.mock('../../hooks/useToast', () => ({
  useToast: () => ({
    toasts: [],
    hideToast: mocks.hideToast,
    success: mocks.toastSuccess,
    error: mocks.toastError,
    warning: mocks.toastWarning,
  }),
}));

vi.mock('../../hooks/useCurrency', () => ({
  useCurrency: () => ({
    currentCurrency: 'NGN',
    setCurrency: vi.fn(),
    toggleCurrency: vi.fn(),
    convertPrice: (price: number) => price,
    formatPrice: (price: number) => `NGN ${price}`,
    convertFromBase: (price: number) => price,
    formatBasePrice: (price: number) => `NGN ${price}`,
    getCurrencySymbol: () => '₦',
    getCurrencyCode: () => 'NGN',
    exchangeRates: { NGN: 1, USD: 0.00067 },
    fetchExchangeRate: vi.fn(),
    isLoadingRates: false,
  }),
}));

vi.mock('../../utils/pricing', () => ({
  formatPriceWithConversion: (amount: number, _srcCurr: string, _targetCurr: string) => `NGN ${amount.toLocaleString()}`,
}));

const mockStats: OrderStats = {
  total_orders: 15,
  total_revenue: 150000,
  pending_orders: 3,
  processing_orders: 5,
  shipped_orders: 4,
  delivered_orders: 2,
  cancelled_orders: 1,
  pending_payment: 6,
  failed_payment: 2,
  average_order_value: 10000,
  orders_today: 5,
  revenue_today: 50000,
};

const makeMockOrder = (overrides: Partial<OrderListItem> = {}): OrderListItem => ({
  id: 'order-1',
  order_number: 'ORD-1001',
  customer: {
    id: 'cust-1',
    email: 'shopper@example.com',
    first_name: 'John',
    last_name: 'Doe',
    phone: '+2348012345678',
  },
  total_amount: 25000,
  currency: 'NGN',
  payment_status: 'paid',
  fulfillment_status: 'order_received',
  created_at: '2026-10-10T12:00:00Z',
  vendor_count: 1,
  item_count: 2,
  ...overrides,
});

describe('AdminOrders page', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.getOrderStats.mockResolvedValue(mockStats);
    mocks.listOrders.mockResolvedValue({
      orders: [makeMockOrder()],
      total: 1,
      page: 1,
      page_size: 20,
      total_pages: 1,
    });
    mocks.exportOrdersCSV.mockResolvedValue(new Blob(['csv content']));
  });

  describe('Default view (Orders Received / Paid scope)', () => {
    it('defaults to paid orders scope on initial load', async () => {
      render(
        <MemoryRouter initialEntries={['/admin/orders']}>
          <AdminOrders />
        </MemoryRouter>
      );

      // Verify listOrders was called with payment_status: 'paid'
      await waitFor(() => {
        expect(mocks.listOrders).toHaveBeenCalledWith(
          expect.objectContaining({
            payment_status: 'paid',
            page: 1,
            page_size: 20,
          })
        );
      });

      // Verify page title and subtitle for Orders Received view
      expect(screen.getByRole('heading', { level: 1, name: 'Orders Received' })).toBeInTheDocument();
      expect(
        screen.getByText('Confirmed and paid customer orders ready for fulfillment')
      ).toBeInTheDocument();

      // Verify sidebar active section is 'orders'
      expect(screen.getByTestId('admin-sidebar')).toHaveAttribute('data-active-section', 'orders');

      // Verify order content rendered
      expect(screen.getByText('ORD-1001')).toBeInTheDocument();
      expect(screen.getByText('John Doe')).toBeInTheDocument();
      expect(screen.getByText('shopper@example.com')).toBeInTheDocument();
      expect(screen.getByText('paid')).toBeInTheDocument();
      expect(screen.getByText('Order Received')).toBeInTheDocument();
    });

    it('displays scoped empty state when no paid orders are found', async () => {
      mocks.listOrders.mockResolvedValue({
        orders: [],
        total: 0,
        page: 1,
        page_size: 20,
        total_pages: 0,
      });

      render(
        <MemoryRouter initialEntries={['/admin/orders']}>
          <AdminOrders />
        </MemoryRouter>
      );

      await waitFor(() => {
        expect(screen.getByText('No orders received yet')).toBeInTheDocument();
      });
    });
  });

  describe('Pending Payments view', () => {
    it('loads pending orders scope when mounted with ?payment_status=pending URL query', async () => {
      mocks.listOrders.mockResolvedValue({
        orders: [
          makeMockOrder({
            id: 'order-pending-1',
            order_number: 'ORD-PEND-2001',
            payment_status: 'pending',
            fulfillment_status: 'order_received',
          }),
        ],
        total: 1,
        page: 1,
        page_size: 20,
        total_pages: 1,
      });

      render(
        <MemoryRouter initialEntries={['/admin/orders?payment_status=pending']}>
          <AdminOrders />
        </MemoryRouter>
      );

      await waitFor(() => {
        expect(mocks.listOrders).toHaveBeenCalledWith(
          expect.objectContaining({
            payment_status: 'pending',
          })
        );
      });

      // Heading and subtitle reflect pending payments
      expect(screen.getByRole('heading', { level: 1, name: 'Pending Payments' })).toBeInTheDocument();
      expect(
        screen.getByText('Orders created at checkout awaiting Paystack payment confirmation')
      ).toBeInTheDocument();

      // Sidebar points to 'orders-pending'
      expect(screen.getByTestId('admin-sidebar')).toHaveAttribute('data-active-section', 'orders-pending');

      // Displays pending order with 'Awaiting Payment' status badge
      expect(screen.getByText('ORD-PEND-2001')).toBeInTheDocument();
      expect(screen.getByText('pending')).toBeInTheDocument();
      expect(screen.getByText('Awaiting Payment')).toBeInTheDocument();
    });

    it('switches to pending payments scope when Pending Payments tab is clicked', async () => {
      render(
        <MemoryRouter initialEntries={['/admin/orders']}>
          <AdminOrders />
        </MemoryRouter>
      );

      await waitFor(() => {
        expect(screen.getByRole('heading', { level: 1, name: 'Orders Received' })).toBeInTheDocument();
      });

      // Click "Pending Payments" tab within Order Views navigation
      const orderViewsNav = screen.getByRole('navigation', { name: 'Order Views' });
      const pendingTab = within(orderViewsNav).getByRole('button', { name: /Pending Payments/i });
      fireEvent.click(pendingTab);

      await waitFor(() => {
        expect(mocks.listOrders).toHaveBeenCalledWith(
          expect.objectContaining({
            payment_status: 'pending',
            page: 1,
          })
        );
      });

      expect(screen.getByRole('heading', { level: 1, name: 'Pending Payments' })).toBeInTheDocument();
    });

    it('displays scoped empty state when no pending payments are found', async () => {
      mocks.listOrders.mockResolvedValue({
        orders: [],
        total: 0,
        page: 1,
        page_size: 20,
        total_pages: 0,
      });

      render(
        <MemoryRouter initialEntries={['/admin/orders?payment_status=pending']}>
          <AdminOrders />
        </MemoryRouter>
      );

      await waitFor(() => {
        expect(screen.getByText('No pending payments found')).toBeInTheDocument();
      });
    });
  });

  describe('Failed and Refunded Payments views', () => {
    it('renders failed orders with distinct "Payment Failed" badge and scoped empty state', async () => {
      mocks.listOrders.mockResolvedValue({
        orders: [
          makeMockOrder({
            id: 'order-failed-1',
            order_number: 'ORD-FAIL-3001',
            payment_status: 'failed',
          }),
        ],
        total: 1,
        page: 1,
        page_size: 20,
        total_pages: 1,
      });

      render(
        <MemoryRouter initialEntries={['/admin/orders?payment_status=failed']}>
          <AdminOrders />
        </MemoryRouter>
      );

      await waitFor(() => {
        expect(mocks.listOrders).toHaveBeenCalledWith(
          expect.objectContaining({
            payment_status: 'failed',
          })
        );
      });

      expect(screen.getByRole('heading', { level: 1, name: 'Failed Payments' })).toBeInTheDocument();
      expect(screen.getByText('Payment Failed')).toBeInTheDocument();
      expect(screen.getByText('failed')).toBeInTheDocument();
      expect(screen.queryByText('Order Received')).not.toBeInTheDocument();
    });

    it('renders refunded orders with distinct "Payment Refunded" badge', async () => {
      mocks.listOrders.mockResolvedValue({
        orders: [
          makeMockOrder({
            id: 'order-ref-1',
            order_number: 'ORD-REF-4001',
            payment_status: 'refunded',
          }),
        ],
        total: 1,
        page: 1,
        page_size: 20,
        total_pages: 1,
      });

      render(
        <MemoryRouter initialEntries={['/admin/orders?payment_status=refunded']}>
          <AdminOrders />
        </MemoryRouter>
      );

      await waitFor(() => {
        expect(mocks.listOrders).toHaveBeenCalledWith(
          expect.objectContaining({
            payment_status: 'refunded',
          })
        );
      });

      expect(screen.getByRole('heading', { level: 1, name: 'Refunded Orders' })).toBeInTheDocument();
      expect(screen.getByText('Payment Refunded')).toBeInTheDocument();
      expect(screen.getByText('refunded')).toBeInTheDocument();
    });

    it('displays scoped empty state for failed payments scope', async () => {
      mocks.listOrders.mockResolvedValue({
        orders: [],
        total: 0,
        page: 1,
        page_size: 20,
        total_pages: 0,
      });

      render(
        <MemoryRouter initialEntries={['/admin/orders?payment_status=failed']}>
          <AdminOrders />
        </MemoryRouter>
      );

      await waitFor(() => {
        expect(screen.getByText('No failed payments found')).toBeInTheDocument();
      });
    });

    it('displays scoped empty state for refunded orders scope', async () => {
      mocks.listOrders.mockResolvedValue({
        orders: [],
        total: 0,
        page: 1,
        page_size: 20,
        total_pages: 0,
      });

      render(
        <MemoryRouter initialEntries={['/admin/orders?payment_status=refunded']}>
          <AdminOrders />
        </MemoryRouter>
      );

      await waitFor(() => {
        expect(screen.getByText('No refunded orders found')).toBeInTheDocument();
      });
    });
  });

  describe('Scoped Actions: Export and Detail Navigation', () => {
    it('passes payment_status: paid when exporting CSV from Orders Received view', async () => {
      render(
        <MemoryRouter initialEntries={['/admin/orders']}>
          <AdminOrders />
        </MemoryRouter>
      );

      await waitFor(() => {
        expect(screen.getByText('ORD-1001')).toBeInTheDocument();
      });

      const exportBtn = screen.getByRole('button', { name: /Export CSV/i });
      fireEvent.click(exportBtn);

      await waitFor(() => {
        expect(mocks.exportOrdersCSV).toHaveBeenCalledWith(
          expect.objectContaining({
            payment_status: 'paid',
          })
        );
        expect(mocks.downloadCSV).toHaveBeenCalledWith(
          expect.any(Blob),
          expect.stringMatching(/^orders_paid_\d{4}-\d{2}-\d{2}\.csv$/)
        );
      });
    });

    it('passes payment_status: pending when exporting CSV from Pending Payments view', async () => {
      mocks.listOrders.mockResolvedValue({
        orders: [
          makeMockOrder({
            id: 'order-pending-1',
            order_number: 'ORD-PEND-2001',
            payment_status: 'pending',
          }),
        ],
        total: 1,
        page: 1,
        page_size: 20,
        total_pages: 1,
      });

      render(
        <MemoryRouter initialEntries={['/admin/orders?payment_status=pending']}>
          <AdminOrders />
        </MemoryRouter>
      );

      await waitFor(() => {
        expect(screen.getByText('ORD-PEND-2001')).toBeInTheDocument();
      });

      const exportBtn = screen.getByRole('button', { name: /Export CSV/i });
      fireEvent.click(exportBtn);

      await waitFor(() => {
        expect(mocks.exportOrdersCSV).toHaveBeenCalledWith(
          expect.objectContaining({
            payment_status: 'pending',
          })
        );
        expect(mocks.downloadCSV).toHaveBeenCalledWith(
          expect.any(Blob),
          expect.stringMatching(/^orders_pending_\d{4}-\d{2}-\d{2}\.csv$/)
        );
      });
    });

    it('navigates to order detail preserving the return path with active scope', async () => {
      mocks.listOrders.mockResolvedValue({
        orders: [
          makeMockOrder({
            id: 'order-pending-123',
            order_number: 'ORD-PEND-123',
            payment_status: 'pending',
          }),
        ],
        total: 1,
        page: 1,
        page_size: 20,
        total_pages: 1,
      });

      render(
        <MemoryRouter initialEntries={['/admin/orders?payment_status=pending']}>
          <AdminOrders />
        </MemoryRouter>
      );

      await waitFor(() => {
        expect(screen.getByText('ORD-PEND-123')).toBeInTheDocument();
      });

      const viewBtn = screen.getByRole('button', { name: 'View →' });
      fireEvent.click(viewBtn);

      expect(mockNavigate).toHaveBeenCalledWith('/admin/orders/order-pending-123', {
        state: { from: '/admin/orders?payment_status=pending' },
      });
    });
  });

  describe('Attention Banner Quick Actions', () => {
    it('switches to pending scope when clicking quick link in attention banner', async () => {
      render(
        <MemoryRouter initialEntries={['/admin/orders']}>
          <AdminOrders />
        </MemoryRouter>
      );

      await waitFor(() => {
        expect(screen.getByText(/View Pending Payments →/i)).toBeInTheDocument();
      });

      const bannerPendingLink = screen.getByText(/View Pending Payments →/i);
      fireEvent.click(bannerPendingLink);

      await waitFor(() => {
        expect(mocks.listOrders).toHaveBeenCalledWith(
          expect.objectContaining({
            payment_status: 'pending',
          })
        );
      });

      expect(screen.getByRole('heading', { level: 1, name: 'Pending Payments' })).toBeInTheDocument();
    });
  });
});
