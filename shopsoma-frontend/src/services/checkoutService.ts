/**
 * Checkout Service
 * Handles all checkout-related API calls
 */
import axios from 'axios';
import { API_BASE_URL, STORAGE_KEYS } from '../config/constants';

const api = axios.create({
  baseURL: API_BASE_URL,
});

// Add auth token to requests
api.interceptors.request.use((config) => {
  const token = localStorage.getItem(STORAGE_KEYS.ACCESS_TOKEN);
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Address Types
export interface Address {
  id: string;
  user_id: string;
  full_name: string;
  phone_number: string;
  address_line1: string;
  address_line2?: string;
  city: string;
  state: string;
  postal_code?: string;
  country: string;
  address_type: 'shipping' | 'billing';
  is_default: boolean;
  created_at: string;
  updated_at: string;
}

export interface CreateAddressData {
  full_name: string;
  phone_number: string;
  address_line1: string;
  address_line2?: string;
  city: string;
  state: string;
  postal_code?: string;
  country?: string;
  address_type?: 'shipping' | 'billing';
  is_default?: boolean;
}

// Shipping Rate Types
export interface ShippingRate {
  id: string;
  name: string;
  description: string;
  base_rate: number;
  country: string;
  state?: string;
  min_delivery_days: number;
  max_delivery_days: number;
}

export interface ShippingCalculation {
  country: string;
  state: string;
  order_value: number;
}

// Promo Code Types
export interface PromoCodeValidation {
  code: string;
  order_subtotal: number;
}

export interface PromoCodeResult {
  valid: boolean;
  code?: string;
  discount_type?: 'percentage' | 'fixed_amount';
  discount_value?: number;
  discount_amount?: number;
  message?: string;
}

// Order Types
export interface OrderItem {
  product_id: string;
  variant_id?: string;
  quantity: number;
}

export interface OrderReviewRequest {
  items: OrderItem[];
  currency: 'NGN' | 'USD';
  shipping_address_id?: string;
  guest_address?: CreateAddressData;
  promo_code?: string;
  shipping_rate_id?: string;
}

export interface OrderSummary {
  currency: 'NGN' | 'USD';
  subtotal: number;
  shipping_cost: number;
  tax_amount: number;
  discount_amount: number;
  total_amount: number;
  items_count: number;
  estimated_delivery_days?: number;
}

export interface OrderReview {
  summary: OrderSummary;
  items: Array<{
    product_id: string;
    product_title: string;
    variant_id?: string;
    variant_details?: Record<string, any>;
    unit_price: number;
    currency: 'NGN' | 'USD';
    quantity: number;
    subtotal: number;
    vendor_name: string;
  }>;
  shipping_rate?: {
    id: string;
    name: string;
    description: string;
    cost: number;
    min_days: number;
    max_days: number;
  };
  applied_promo?: {
    code: string;
    discount_percent?: number;
    discount_amount: number;
  };
}

export interface CreateOrderData {
  items: OrderItem[];
  currency: 'NGN' | 'USD';
  shipping_address_id?: string;
  billing_address_id?: string;
  guest_address?: CreateAddressData;
  customer_email?: string;
  customer_notes?: string;
  promo_code?: string;
  shipping_rate_id?: string;
}

export interface Order {
  id: string;
  order_number: string;
  customer_id: string;
  currency?: 'NGN' | 'USD';
  shipping_address_id?: string;
  billing_address_id?: string;
  subtotal: number;
  shipping_cost: number;
  tax_amount: number;
  discount_amount: number;
  total_amount: number;
  payment_status: string;
  fulfillment_status: string;
  created_at: string;
  items: Array<any>;
}

/**
 * Address Management
 */
export const checkoutService = {
  // Get all addresses
  async getAddresses(): Promise<{ addresses: Address[]; total: number }> {
    const response = await api.get('/addresses');
    return response.data;
  },

  // Create new address
  async createAddress(data: CreateAddressData): Promise<Address> {
    const response = await api.post('/addresses', data);
    return response.data;
  },

  // Update address
  async updateAddress(id: string, data: Partial<CreateAddressData>): Promise<Address> {
    const response = await api.put(`/addresses/${id}`, data);
    return response.data;
  },

  // Delete address
  async deleteAddress(id: string): Promise<void> {
    await api.delete(`/addresses/${id}`);
  },

  // Set default address
  async setDefaultAddress(id: string): Promise<Address> {
    const response = await api.post(`/addresses/${id}/set-default`);
    return response.data;
  },

  /**
   * Shipping Rates
   */
  // Calculate shipping
  async calculateShipping(data: ShippingCalculation): Promise<{
    available_rates: ShippingRate[];
    recommended_rate?: ShippingRate;
  }> {
    const response = await api.post('/shipping-rates/calculate', data);
    return response.data;
  },

  /**
   * Promo Codes
   */
  // Validate promo code
  async validatePromoCode(data: PromoCodeValidation): Promise<PromoCodeResult> {
    const response = await api.post('/promo-codes/validate', data);
    return response.data;
  },

  /**
   * Orders
   */
  // Review order before creation
  async reviewOrder(data: OrderReviewRequest): Promise<OrderReview> {
    const response = await api.post('/orders/review', data);
    return response.data;
  },

  // Create order
  async createOrder(data: CreateOrderData): Promise<Order> {
    const response = await api.post('/orders', data);
    return response.data;
  },

  // Get user orders
  async getOrders(page = 1, pageSize = 20): Promise<{
    orders: Order[];
    total: number;
    page: number;
    page_size: number;
  }> {
    const response = await api.get('/orders', {
      params: { page, page_size: pageSize },
    });
    return response.data;
  },

  // Get order by ID
  async getOrder(id: string): Promise<Order> {
    const response = await api.get(`/orders/${id}`);
    return response.data;
  },

  // Cancel order
  async cancelOrder(id: string, reason: string): Promise<Order> {
    const response = await api.post(`/orders/${id}/cancel`, {
      cancellation_reason: reason,
    });
    return response.data;
  },
};
