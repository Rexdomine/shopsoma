import api from './api';

export type OrderStatus =
  | 'order_placed'
  | 'pending_confirmation'
  | 'picked_up'
  | 'in_transit'
  | 'out_for_delivery'
  | 'delivered'
  | 'delivery_failed'
  | 'returned'
  | 'cancelled';

export interface TrackingHistory {
  status: OrderStatus;
  description: string;
  occurred_at: string;
}

export interface OrderTracking {
  order_id: string;
  order_number: string;
  tracking_id: string;
  amount: number;
  currency: string;
  updated_at: string;
  current_status: OrderStatus;
  history: TrackingHistory[];
}

export const orderService = {
  async getOrderTracking(orderId: string): Promise<OrderTracking> {
    const response = await api.get(`/orders/${orderId}/tracking`);
    return response.data;
  },
};

export const buildMockTracking = (orderId: string): OrderTracking => {
  const trackingId = `GB${orderId.replace(/[^A-Za-z0-9]/g, '').slice(-8).toUpperCase() || '123821AX'}`;
  const today = new Date();

  return {
    order_id: orderId,
    order_number: orderId,
    tracking_id: trackingId,
    amount: 85000,
    currency: 'NGN',
    updated_at: today.toISOString(),
    current_status: 'pending_confirmation',
    history: [
      {
        status: 'order_placed',
        description: 'Order confirmed by Shopsoma',
        occurred_at: new Date(today.getTime() - 3 * 24 * 60 * 60 * 1000).toISOString(),
      },
      {
        status: 'pending_confirmation',
        description: 'Processing and awaiting vendor confirmation',
        occurred_at: new Date(today.getTime() - 2 * 24 * 60 * 60 * 1000).toISOString(),
      },
    ],
  };
};

// Vendor Order Management Types
export type VendorOrderStatus = 'pending' | 'confirmed' | 'processing' | 'shipped' | 'delivered' | 'cancelled' | 'returned';

export type PickupStatus =
  | 'scheduled'
  | 'in_transit'
  | 'delivered_to_qc'
  | 'qc_approved'
  | 'qc_rejected'
  | 'shipped_to_customer'
  | 'completed'
  | 'cancelled';

export interface VendorPickup {
  id: string;
  order_type: 'rtw' | 'made_to_order' | 'custom';
  scheduled_pickup_date: string | null;
  actual_pickup_date: string | null;
  pickup_window_start: string | null;
  pickup_window_end: string | null;
  courier_name: string | null;
  rider_id: string | null;
  pickup_address: string | null;
  logistics_partner: string | null;
  tracking_number: string | null;
  status: PickupStatus;
  qc_center_arrival_date: string | null;
  qc_approved_date: string | null;
  qc_notes: string | null;
  vendor_notes: string | null;
  created_at: string | null;
  completed_at: string | null;
}

export interface VendorOrderItem {
  id: string;
  order_id: string;
  product_id: string;
  product_title: string;
  variant_details: any | null;
  unit_price: number;
  quantity: number;
  subtotal: number;
  commission_rate: number;
  commission_amount: number;
  vendor_payout: number;
  fulfillment_status: string;
  created_at: string;
  product_image_url?: string;
  pickup: VendorPickup | null;
}

export interface VendorOrder {
  id: string;
  order_number: string;
  items: VendorOrderItem[];
  vendor_business_name: string;
  customer_name: string;
  customer_email: string;
  shipping_address: {
    address_line1: string | null;
    address_line2?: string | null;
    city: string | null;
    state: string | null;
    postal_code?: string | null;
    country: string | null;
  } | null;
  payment_status: string;
  fulfillment_status: string;
  created_at: string;
  confirmed_at: string | null;
  customer_notes?: string | null;
}

export interface VendorOrderListResponse {
  orders: VendorOrder[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

/**
 * Get orders for the vendor
 */
export const getVendorOrders = async (params: {
  page?: number;
  page_size?: number;
  search?: string;
  status?: string;
}): Promise<VendorOrderListResponse> => {
  const { page = 1, page_size = 20, search = '', status } = params;

  const response = await api.get('/vendor/orders', {
    params: {
      page,
      page_size,
      search: search || undefined,
      status: status || undefined,
    },
  });

  return response.data;
};

/**
 * Get a specific vendor order by ID
 */
export const getVendorOrder = async (orderId: string): Promise<VendorOrder> => {
  const response = await api.get(`/vendor/orders/${orderId}`);
  return response.data;
};

/**
 * Update order item fulfillment status
 */
// NOTE: Vendors cannot update fulfillment status
// Fulfillment is managed by Shopsoma logistics team through admin panel
// This function has been removed

/**
 * Export orders to CSV
 */
export const exportOrdersToCSV = (orders: VendorOrder[]): void => {
  const headers = ['Order Number', 'Customer Name', 'Items', 'Total Payout', 'Status', 'Created At'];
  const rows = orders.map((order) => {
    const totalPayout = order.items.reduce((sum, item) => sum + item.vendor_payout, 0);
    const itemsSummary = order.items.map(item => `${item.product_title} (x${item.quantity})`).join('; ');

    return [
      order.order_number,
      order.customer_name,
      itemsSummary,
      `₦${totalPayout.toFixed(2)}`,
      order.fulfillment_status,
      new Date(order.created_at).toLocaleDateString(),
    ];
  });

  const csvContent = [
    headers.join(','),
    ...rows.map((row) => row.map((cell) => `"${cell}"`).join(',')),
  ].join('\n');

  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
  const link = document.createElement('a');
  const url = URL.createObjectURL(blob);
  link.setAttribute('href', url);
  link.setAttribute('download', `vendor_orders_${new Date().toISOString().split('T')[0]}.csv`);
  link.style.visibility = 'hidden';
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
};
