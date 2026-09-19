import api from './api';

export type ShippingQuoteStatus = 'available' | 'selected' | 'expired' | 'superseded';

export interface CustomerShippingQuoteOption {
  id: string;
  service_label: string;
  total_amount: string;
  currency: string;
  transit_days?: number | null;
  delivery_date?: string | null;
}

export interface CustomerShippingQuote {
  id: string;
  order_id: string;
  currency: string;
  expires_at: string;
  created_at: string;
  status: ShippingQuoteStatus;
  selected_option_id?: string | null;
  options: CustomerShippingQuoteOption[];
}

const idempotencyHeaders = (key: string) => ({
  headers: { 'X-Idempotency-Key': key },
});

export const shippingQuoteService = {
  async listQuotes(orderId: string): Promise<CustomerShippingQuote[]> {
    const response = await api.get<CustomerShippingQuote[]>(`/orders/${orderId}/shipping-quotes`);
    return response.data;
  },

  async createQuote(orderId: string, idempotencyKey: string): Promise<CustomerShippingQuote> {
    const response = await api.post<CustomerShippingQuote>(
      `/orders/${orderId}/shipping-quotes`,
      undefined,
      idempotencyHeaders(idempotencyKey),
    );
    return response.data;
  },

  async selectOption(
    orderId: string,
    quoteId: string,
    optionId: string,
    idempotencyKey: string,
  ): Promise<CustomerShippingQuote> {
    const response = await api.post<CustomerShippingQuote>(
      `/orders/${orderId}/shipping-quotes/${quoteId}/options/${optionId}/select`,
      undefined,
      idempotencyHeaders(idempotencyKey),
    );
    return response.data;
  },
};
