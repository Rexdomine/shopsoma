/**
 * Payment Service
 * Handles all payment-related API calls
 */
import axios from 'axios';
import { API_BASE_URL } from '../config/constants';

const api = axios.create({
  baseURL: API_BASE_URL,
});

// Add auth token to requests
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Payment Types
export interface PaymentInitializeRequest {
  order_id: string;
  email: string;
  callback_url?: string;
}

export interface PaymentInitializeResponse {
  status: boolean;
  message: string;
  authorization_url: string;
  access_code: string;
  reference: string;
}

export interface PaymentVerifyRequest {
  reference: string;
}

export interface PaymentVerifyResponse {
  status: boolean;
  message: string;
  data?: any;
}

export interface Payment {
  id: string;
  order_id: string;
  transaction_id: string;
  payment_gateway: string;
  payment_method: string;
  amount: number;
  currency: string;
  status: string;
  gateway_response: any;
  created_at: string;
  completed_at?: string;
  failed_at?: string;
  failure_reason?: string;
}

/**
 * Payment Service
 */
export const paymentService = {
  /**
   * Initialize a payment with Paystack
   */
  async initializePayment(data: PaymentInitializeRequest): Promise<PaymentInitializeResponse> {
    const response = await api.post('/payments/initialize', data);
    return response.data;
  },

  /**
   * Verify a payment
   */
  async verifyPayment(data: PaymentVerifyRequest): Promise<PaymentVerifyResponse> {
    const response = await api.post('/payments/verify', data);
    return response.data;
  },

  /**
   * Get payment details by ID
   */
  async getPayment(paymentId: string): Promise<Payment> {
    const response = await api.get(`/payments/${paymentId}`);
    return response.data;
  },
};
