import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import OrderStats from './OrderStats';
import type { OrderStats as OrderStatsType } from '../../services/adminOrderService';

const mockStats: OrderStatsType = {
  total_orders: 5,
  total_revenue: 125000,
  pending_orders: 3,
  processing_orders: 1,
  shipped_orders: 1,
  delivered_orders: 0,
  cancelled_orders: 0,
  pending_payment: 2,
  failed_payment: 1,
  average_order_value: 25000,
  orders_today: 2,
  revenue_today: 50000,
};

describe('OrderStats Component', () => {
  it('renders Orders Received card with paid & awaiting processing subtext', () => {
    render(<OrderStats stats={mockStats} />);

    expect(screen.getByText('Orders Received')).toBeInTheDocument();
    expect(screen.getByText('Paid & awaiting processing')).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument();
  });

  it('renders Total Revenue and order counts', () => {
    render(<OrderStats stats={mockStats} />);

    expect(screen.getByText('Total Revenue')).toBeInTheDocument();
    expect(screen.getByText('5 orders')).toBeInTheDocument();
  });

  it('renders payment attention section when pending or failed payments exist', () => {
    render(<OrderStats stats={mockStats} />);

    expect(screen.getByText('Payment Attention Required')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();
    expect(screen.getByText(/orders with pending payment/i)).toBeInTheDocument();
  });
});
