import axios from 'axios';
import { API_BASE_URL } from '../config/constants';

const api = axios.create({
  baseURL: API_BASE_URL,
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export type OrderStatus =
  | 'order_placed'
  | 'pending_confirmation'
  | 'waiting_to_ship'
  | 'shipped'
  | 'out_for_delivery'
  | 'delivered';

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
