import api from './api';

export interface PaymentMethod {
  id: string;
  vendor_id: string;
  account_type: string | null;
  bank_name: string;
  account_number: string;
  masked_account: string;
  account_holder: string;
  tin: string | null;
  is_default: boolean;
  created_at: string;
  updated_at: string;
}

export interface PaymentMethodCreate {
  account_type?: string;
  bank_name: string;
  account_number: string;
  account_holder: string;
  tin?: string;
  is_default?: boolean;
}

export const vendorPaymentMethodsService = {
  /**
   * Get all payment methods for the current vendor
   */
  async list(): Promise<PaymentMethod[]> {
    try {
      const response = await api.get('/vendor/payment-methods');
      return response.data;
    } catch (error: any) {
      const message = error?.response?.data?.detail || 'Failed to fetch payment methods';
      throw new Error(message);
    }
  },

  /**
   * Create a new payment method
   */
  async create(data: PaymentMethodCreate): Promise<PaymentMethod> {
    try {
      const response = await api.post('/vendor/payment-methods', data);
      return response.data;
    } catch (error: any) {
      const message = error?.response?.data?.detail || 'Failed to create payment method';
      throw new Error(message);
    }
  },

  /**
   * Set a payment method as default
   */
  async setDefault(methodId: string): Promise<PaymentMethod> {
    try {
      const response = await api.post(`/vendor/payment-methods/${methodId}/set-default`);
      return response.data;
    } catch (error: any) {
      const message = error?.response?.data?.detail || 'Failed to set default payment method';
      throw new Error(message);
    }
  },

  /**
   * Delete a payment method
   */
  async delete(methodId: string): Promise<void> {
    try {
      await api.delete(`/vendor/payment-methods/${methodId}`);
    } catch (error: any) {
      const message = error?.response?.data?.detail || 'Failed to delete payment method';
      throw new Error(message);
    }
  },
};
