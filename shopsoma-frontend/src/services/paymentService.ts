/**
 * Payment Service
 * Handles payment-related API calls including customer portal management
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

export interface CustomerPortalResponse {
  url: string;
  provider: 'paystack' | 'stripe';
}

export type PaymentGateway = 'paystack' | 'stripe';
export type Currency = 'NGN' | 'USD';

export interface InitializePaymentPayload {
  order_id: string;
  email: string;
  payment_gateway: PaymentGateway;
  currency: Currency;
  callback_url?: string;
}

export interface InitializePaymentResponse {
  status: boolean;
  message: string;
  authorization_url?: string;
  access_code?: string;
  reference?: string;
  client_secret?: string;
  payment_intent_id?: string;
  checkout_url?: string;
  payment_gateway: string;
}

export interface VerifyPaymentPayload {
  reference?: string;
  payment_intent_id?: string;
  payment_gateway: PaymentGateway;
}

export interface VerifyPaymentResponse {
  status: boolean;
  message: string;
  data?: Record<string, unknown>;
}

export const paymentService = {
  /**
   * Initialize a payment session for an order
   */
  async initializePayment(payload: InitializePaymentPayload): Promise<InitializePaymentResponse> {
    const response = await api.post('/payments/initialize', payload);
    return response.data;
  },

  /**
   * Verify a payment after gateway callback
   */
  async verifyPayment(payload: VerifyPaymentPayload): Promise<VerifyPaymentResponse> {
    const response = await api.post('/payments/verify', payload);
    return response.data;
  },

  /**
   * Get Paystack Customer Portal URL
   * Returns a URL to Paystack's hosted customer portal where users can manage their saved cards
   */
  async getPaystackCustomerPortalUrl(): Promise<CustomerPortalResponse> {
    const response = await api.post('/payments/paystack/customer-portal');
    return response.data;
  },

  /**
   * Get Stripe Customer Portal URL
   * Returns a URL to Stripe's hosted customer portal where users can manage their saved cards
   */
  async getStripeCustomerPortalUrl(): Promise<CustomerPortalResponse> {
    const response = await api.post('/payments/stripe/customer-portal');
    return response.data;
  },
};
