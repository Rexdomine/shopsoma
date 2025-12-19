/**
 * Order Status Message Mapping
 * Provides vendor and customer-facing labels and messages for order statuses
 */

// Define FulfillmentStatus type locally to avoid circular dependency
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

// ============================================================================
// VENDOR-FACING MESSAGES
// ============================================================================

export const VENDOR_STATUS_LABELS: Record<FulfillmentStatus, string> = {
  order_received: 'New Order - Start Preparing',
  preparing_for_pickup: 'Pack Order - Awaiting Rider',
  pickup_scheduled: 'Pickup Booked',
  picked_up: 'Items Handed Over',
  in_transit: 'On Way to Customer',
  out_for_delivery: 'Out for Delivery',
  delivered: 'Delivered Successfully',
  delivery_failed: 'Delivery Failed',
  returned: 'Order Returned',
  cancelled: 'Order Cancelled',
};

export const VENDOR_STATUS_MESSAGES: Record<FulfillmentStatus, string> = {
  order_received: 'A new order has been placed. Please begin preparing items for pickup.',
  preparing_for_pickup: 'Please pack the order items. A pickup will be scheduled soon.',
  pickup_scheduled: 'Pickup has been scheduled. Please have items ready during the pickup window.',
  picked_up: 'Your items have been handed over to the courier successfully.',
  in_transit: 'Items are in transit to the customer.',
  out_for_delivery: 'Items are out for delivery to the customer.',
  delivered: 'The order has been delivered to the customer. Payment will be processed soon.',
  delivery_failed: 'Delivery attempt failed. Our logistics team will retry delivery.',
  returned: 'The order has been returned. Please contact support for details.',
  cancelled: 'This order has been cancelled.',
};

// ============================================================================
// CUSTOMER-FACING MESSAGES
// ============================================================================

export const CUSTOMER_STATUS_LABELS: Record<FulfillmentStatus, string> = {
  order_received: 'Order Confirmed',
  preparing_for_pickup: 'Order Being Prepared',
  pickup_scheduled: 'Pickup Arranged',
  picked_up: 'Order Dispatched',
  in_transit: 'In Transit',
  out_for_delivery: 'Out for Delivery',
  delivered: 'Delivered',
  delivery_failed: 'Delivery Attempt Failed',
  returned: 'Order Returned',
  cancelled: 'Order Cancelled',
};

export const CUSTOMER_STATUS_MESSAGES: Record<FulfillmentStatus, string> = {
  order_received: 'Your order has been confirmed and is being processed.',
  preparing_for_pickup: 'Your order is being prepared by the vendor.',
  pickup_scheduled: 'Pickup from vendor has been arranged. Your order will be dispatched soon.',
  picked_up: 'Your order has been dispatched and is on its way to you.',
  in_transit: 'Your order is in transit and will arrive soon.',
  out_for_delivery: 'Your order is out for delivery and will arrive today.',
  delivered: 'Your order has been delivered. Thank you for shopping with us!',
  delivery_failed: 'We couldn\'t deliver your order. We\'ll try again soon or contact you.',
  returned: 'Your order has been returned. A refund will be processed.',
  cancelled: 'Your order has been cancelled. A refund will be processed if payment was made.',
};

// ============================================================================
// ADMIN-FACING MESSAGES (Neutral/Technical)
// ============================================================================

export const ADMIN_STATUS_LABELS: Record<FulfillmentStatus, string> = {
  order_received: 'Order Received',
  preparing_for_pickup: 'Preparing for Pickup',
  pickup_scheduled: 'Pickup Scheduled',
  picked_up: 'Picked Up',
  in_transit: 'In Transit',
  out_for_delivery: 'Out for Delivery',
  delivered: 'Delivered',
  delivery_failed: 'Delivery Failed',
  returned: 'Returned',
  cancelled: 'Cancelled',
};

// ============================================================================
// STATUS BADGE COLORS
// ============================================================================

export interface StatusBadgeConfig {
  bgColor: string;
  textColor: string;
  label: string;
}

export const getStatusBadgeConfig = (
  status: FulfillmentStatus,
  audience: 'admin' | 'vendor' | 'customer' = 'admin'
): StatusBadgeConfig => {
  // Get appropriate label based on audience
  let label: string;
  switch (audience) {
    case 'vendor':
      label = VENDOR_STATUS_LABELS[status];
      break;
    case 'customer':
      label = CUSTOMER_STATUS_LABELS[status];
      break;
    default:
      label = ADMIN_STATUS_LABELS[status];
  }

  // Determine colors based on status
  const colorMap: Record<FulfillmentStatus, { bgColor: string; textColor: string }> = {
    order_received: { bgColor: 'bg-blue-100', textColor: 'text-blue-800' },
    preparing_for_pickup: { bgColor: 'bg-yellow-100', textColor: 'text-yellow-800' },
    pickup_scheduled: { bgColor: 'bg-purple-100', textColor: 'text-purple-800' },
    picked_up: { bgColor: 'bg-indigo-100', textColor: 'text-indigo-800' },
    in_transit: { bgColor: 'bg-cyan-100', textColor: 'text-cyan-800' },
    out_for_delivery: { bgColor: 'bg-orange-100', textColor: 'text-orange-800' },
    delivered: { bgColor: 'bg-green-100', textColor: 'text-green-800' },
    delivery_failed: { bgColor: 'bg-red-100', textColor: 'text-red-800' },
    returned: { bgColor: 'bg-gray-100', textColor: 'text-gray-800' },
    cancelled: { bgColor: 'bg-gray-100', textColor: 'text-gray-800' },
  };

  const colors = colorMap[status] || { bgColor: 'bg-gray-100', textColor: 'text-gray-800' };

  return {
    ...colors,
    label,
  };
};

// ============================================================================
// HELPER FUNCTIONS
// ============================================================================

/**
 * Get vendor-facing label for a status
 */
export const getVendorStatusLabel = (status: FulfillmentStatus): string => {
  return VENDOR_STATUS_LABELS[status] || status.replace(/_/g, ' ').toUpperCase();
};

/**
 * Get vendor-facing message for a status
 */
export const getVendorStatusMessage = (status: FulfillmentStatus): string => {
  return VENDOR_STATUS_MESSAGES[status] || '';
};

/**
 * Get customer-facing label for a status
 */
export const getCustomerStatusLabel = (status: FulfillmentStatus): string => {
  return CUSTOMER_STATUS_LABELS[status] || status.replace(/_/g, ' ').toUpperCase();
};

/**
 * Get customer-facing message for a status
 */
export const getCustomerStatusMessage = (status: FulfillmentStatus): string => {
  return CUSTOMER_STATUS_MESSAGES[status] || '';
};

/**
 * Get admin-facing label for a status
 */
export const getAdminStatusLabel = (status: FulfillmentStatus): string => {
  return ADMIN_STATUS_LABELS[status] || status.replace(/_/g, ' ').toUpperCase();
};

/**
 * Check if a status requires action from vendor
 */
export const requiresVendorAction = (status: FulfillmentStatus): boolean => {
  return ['order_received', 'preparing_for_pickup', 'pickup_scheduled'].includes(status);
};

/**
 * Check if a status is a terminal state (order complete/cancelled)
 */
export const isTerminalStatus = (status: FulfillmentStatus): boolean => {
  return ['delivered', 'returned', 'cancelled'].includes(status);
};

/**
 * Get the next logical status in the workflow
 */
export const getNextStatus = (currentStatus: FulfillmentStatus): FulfillmentStatus | null => {
  const workflow: Partial<Record<FulfillmentStatus, FulfillmentStatus>> = {
    order_received: 'preparing_for_pickup',
    preparing_for_pickup: 'pickup_scheduled',
    pickup_scheduled: 'picked_up',
    picked_up: 'in_transit',
    in_transit: 'out_for_delivery',
    out_for_delivery: 'delivered',
  };

  return workflow[currentStatus] || null;
};
