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

let refreshPromise: Promise<string> | null = null;

api.interceptors?.response?.use(
  (response) => response,
  async (error) => {
    const originalRequest = error?.config as any;
    if (error?.response?.status === 401 && originalRequest && !originalRequest._retry) {
      const refreshToken = localStorage.getItem(STORAGE_KEYS.REFRESH_TOKEN);
      if (refreshToken) {
        originalRequest._retry = true;
        try {
          if (!refreshPromise) {
            refreshPromise = (async () => {
              try {
                const response = await axios.post(`${API_BASE_URL}/auth/refresh`, {
                  refresh_token: refreshToken,
                });
                const { access_token, refresh_token: nextRefreshToken } = response.data;
                localStorage.setItem(STORAGE_KEYS.ACCESS_TOKEN, access_token);
                if (nextRefreshToken) {
                  localStorage.setItem(STORAGE_KEYS.REFRESH_TOKEN, nextRefreshToken);
                }
                return access_token;
              } finally {
                refreshPromise = null;
              }
            })();
          }
          const newAccessToken = await refreshPromise;
          originalRequest.headers = originalRequest.headers || {};
          originalRequest.headers.Authorization = `Bearer ${newAccessToken}`;
          return api(originalRequest);
        } catch {
          localStorage.removeItem(STORAGE_KEYS.ACCESS_TOKEN);
          localStorage.removeItem(STORAGE_KEYS.REFRESH_TOKEN);
          localStorage.removeItem(STORAGE_KEYS.USER);
        }
      } else {
        localStorage.removeItem(STORAGE_KEYS.ACCESS_TOKEN);
        localStorage.removeItem(STORAGE_KEYS.USER);
      }
    }
    return Promise.reject(error);
  },
);

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
  currency?: Currency;
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
  amount: string;
  amount_minor: number;
  currency: Currency;
  provider_payload?: {
    authorization_url?: string;
    access_code?: string;
    client_secret?: string;
    payment_intent_id?: string;
  };
}

export function buildPaystackWidgetConfig(
  initialization: InitializePaymentResponse,
  customer: { email: string; key: string },
) {
  if (!initialization.reference || !Number.isSafeInteger(initialization.amount_minor)) {
    throw new Error('Payment initialization response is incomplete');
  }
  return {
    key: customer.key,
    email: customer.email,
    amount: initialization.amount_minor,
    currency: initialization.currency,
    ref: initialization.reference,
    access_code: initialization.provider_payload?.access_code ?? initialization.access_code,
  };
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
  async initializePayment(payload: InitializePaymentPayload, capability?: string): Promise<InitializePaymentResponse> {
    const response = await api.post(
      '/payments/initialize',
      payload,
      capability ? { headers: { 'X-ShopSoma-Checkout-Capability': capability } } : undefined,
    );
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
