/**
 * Admin Order Management Service
 * API calls for super user order management
 */
import api from './api';

// ============================================================================
// TYPES
// ============================================================================

export type PaymentStatus = 'pending' | 'paid' | 'failed' | 'refunded';
export type FulfillmentStatus =
  | 'order_received'
  | 'preparing_for_pickup'
  | 'pickup_scheduled'
  | 'picked_up'
  | 'in_transit'
  | 'out_for_delivery'
  | 'delivered'
  | 'delivery_failed'
  | 'returned'
  | 'cancelled';
export type PickupStatus =
  | 'scheduled'
  | 'in_transit'
  | 'delivered_to_qc'
  | 'qc_approved'
  | 'qc_rejected'
  | 'shipped_to_customer'
  | 'completed'
  | 'cancelled';

export interface CustomerInfo {
  id: string;
  first_name?: string;
  last_name?: string;
  email: string;
  phone?: string;
}

export interface VendorInfo {
  id: string;
  business_name: string;
  contact_email?: string;
  contact_phone?: string;
}

export interface AddressInfo {
  id: string;
  full_name: string;
  phone: string;
  street_address: string;
  city: string;
  state: string;
  country: string;
  postal_code: string;
}

export interface OrderItemDetail {
  id: string;
  product_id: string;
  product_title: string;
  product_image_url?: string;
  variant_details?: Record<string, any>;
  unit_price: number;
  quantity: number;
  subtotal: number;
  commission_rate: number;
  commission_amount: number;
  vendor_payout: number;
  fulfillment_status: FulfillmentStatus;
  vendor: VendorInfo;
}

export interface PickupInfo {
  id: string;
  status: PickupStatus;
  scheduled_pickup_date?: string;
  actual_pickup_date?: string;
  pickup_window_start?: string;
  pickup_window_end?: string;
  logistics_partner?: string;
  courier_name?: string;
  rider_id?: string;
  tracking_number?: string;
  qc_center_arrival_date?: string;
  qc_approved_date?: string;
  qc_rejected_date?: string;
  qc_notes?: string;
  vendor_notes?: string;
  admin_notes?: string;
}

export interface OrderListItem {
  id: string;
  order_number: string;
  customer: CustomerInfo;
  total_amount: number;
  payment_status: PaymentStatus;
  fulfillment_status: FulfillmentStatus;
  created_at: string;
  vendor_count: number;
  item_count: number;
}

export interface OrderDetail {
  id: string;
  order_number: string;
  customer: CustomerInfo;
  shipping_address?: AddressInfo;
  billing_address?: AddressInfo;
  subtotal: number;
  shipping_cost: number;
  tax_amount: number;
  discount_amount: number;
  total_amount: number;
  payment_status: PaymentStatus;
  fulfillment_status: FulfillmentStatus;
  delivery_provider?: string;
  tracking_number?: string;
  estimated_delivery_date?: string;
  delivered_at?: string;
  customer_notes?: string;
  admin_notes?: string;
  created_at: string;
  updated_at: string;
  confirmed_at?: string;
  cancelled_at?: string;
  cancellation_reason?: string;
  items: OrderItemDetail[];
  pickups: PickupInfo[];
}

export interface OrderStats {
  total_orders: number;
  total_revenue: number;
  pending_orders: number;
  processing_orders: number;
  shipped_orders: number;
  delivered_orders: number;
  cancelled_orders: number;
  pending_payment: number;
  failed_payment: number;
  average_order_value: number;
  orders_today: number;
  revenue_today: number;
}

export interface PaginatedOrders {
  orders: OrderListItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface OrderFilterParams {
  page?: number;
  page_size?: number;
  search?: string;
  payment_status?: PaymentStatus;
  fulfillment_status?: FulfillmentStatus;
  vendor_id?: string;
  date_from?: string;
  date_to?: string;
}

export interface OrderStatusUpdate {
  fulfillment_status: FulfillmentStatus;
  admin_notes?: string;
  pickup_window_start?: string;
  pickup_window_end?: string;
  courier_name?: string;
  rider_id?: string;
}

export interface ShippingInfoUpdate {
  delivery_provider?: string;
  tracking_number?: string;
  estimated_delivery_date?: string;
  admin_notes?: string;
}

export interface PickupStatusUpdate {
  pickup_status?: PickupStatus;
  scheduled_pickup_date?: string;
  actual_pickup_date?: string;
  pickup_window_start?: string;
  pickup_window_end?: string;
  logistics_partner?: string;
  courier_name?: string;
  rider_id?: string;
  tracking_number?: string;
  qc_notes?: string;
  admin_notes?: string;
}

export interface BulkStatusUpdate {
  order_ids: string[];
  fulfillment_status: FulfillmentStatus;
  admin_notes?: string;
}

export interface RefundRequest {
  reason: string;
  refund_amount?: number;
  refund_type: 'full' | 'partial';
  admin_notes?: string;
}

export interface CancelOrderRequest {
  cancellation_reason: string;
  refund?: boolean;
  admin_notes?: string;
}

// ============================================================================
// API FUNCTIONS
// ============================================================================

/**
 * Get order statistics
 */
export const getOrderStats = async (): Promise<OrderStats> => {
  const response = await api.get<OrderStats>('/admin/orders/stats');
  return response.data;
};

/**
 * List orders with filters and pagination
 */
export const listOrders = async (params?: OrderFilterParams): Promise<PaginatedOrders> => {
  const response = await api.get<PaginatedOrders>('/admin/orders', { params });
  return response.data;
};

/**
 * Get order detail
 */
export const getOrderDetail = async (orderId: string): Promise<OrderDetail> => {
  const response = await api.get<OrderDetail>(`/admin/orders/${orderId}`);
  return response.data;
};

/**
 * Update order status
 */
export const updateOrderStatus = async (
  orderId: string,
  data: OrderStatusUpdate
): Promise<OrderDetail> => {
  const response = await api.patch<OrderDetail>(`/admin/orders/${orderId}/status`, data);
  return response.data;
};

/**
 * Update shipping information
 */
export const updateShippingInfo = async (
  orderId: string,
  data: ShippingInfoUpdate
): Promise<OrderDetail> => {
  const response = await api.patch<OrderDetail>(`/admin/orders/${orderId}/shipping`, data);
  return response.data;
};

/**
 * Update pickup status
 */
export const updatePickupStatus = async (
  orderId: string,
  pickupId: string,
  data: PickupStatusUpdate
): Promise<OrderDetail> => {
  const response = await api.patch<OrderDetail>(
    `/admin/orders/${orderId}/pickup/${pickupId}`,
    data
  );
  return response.data;
};

/**
 * Bulk update order statuses
 */
export const bulkUpdateStatus = async (data: BulkStatusUpdate): Promise<{ success: boolean; updated_count: number; message: string }> => {
  const response = await api.patch('/admin/orders/bulk/status', data);
  return response.data;
};

/**
 * Cancel order
 */
export const cancelOrder = async (
  orderId: string,
  data: CancelOrderRequest
): Promise<{ success: boolean; message: string; order_id: string; order_number: string }> => {
  const response = await api.post(`/admin/orders/${orderId}/cancel`, data);
  return response.data;
};

/**
 * Process refund
 */
export const processRefund = async (
  orderId: string,
  data: RefundRequest
): Promise<{ success: boolean; message: string; order_id: string; order_number: string; refund_amount: number }> => {
  const response = await api.post(`/admin/orders/${orderId}/refund`, data);
  return response.data;
};

/**
 * Export orders to CSV
 */
export const exportOrdersCSV = async (params?: {
  payment_status?: PaymentStatus;
  fulfillment_status?: FulfillmentStatus;
  date_from?: string;
  date_to?: string;
}): Promise<Blob> => {
  const response = await api.get('/admin/orders/export/csv', {
    params,
    responseType: 'blob',
  });
  return response.data;
};

/**
 * Download CSV file
 */
export const downloadCSV = (blob: Blob, filename: string = 'orders.csv') => {
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.URL.revokeObjectURL(url);
};
