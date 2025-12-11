import api from './api';

export interface VendorProfile {
  id: string;
  user_id: string;
  business_name: string;
  business_description: string | null;
  business_address: string | null;
  business_phone: string | null;
  logo_url: string | null;
  returning_address: string | null;
  open_days: string[] | null;
  open_hour: string | null;
  close_hour: string | null;
  secondary_contacts: Array<{phone: string; email: string}> | null;
  kyc_status: string;
  kyc_submitted_at: string | null;
  bank_name: string | null;
  bank_account_number: string | null;
  bank_account_name: string | null;
  commission_rate: string;
  approved: boolean;
  approved_at: string | null;
  store_active: boolean;
  store_paused_at: string | null;
  store_deleted_at: string | null;
  is_onboarding: boolean;
  brand_info_completed: boolean;
  payout_info_completed: boolean;
  onboarding_completed_at: string | null;
  total_products: number;
  total_orders: number;
  total_revenue: string;
  created_at: string;
  updated_at: string;
}

export interface BrandInfoData {
  business_phone: string;
  email?: string;
  business_description?: string;
  logo_url?: string;
  shipping_country?: string;
  shipping_address: string;
  returning_country?: string;
  returning_address?: string;
  open_days: string[];
  open_hour: string;
  close_hour: string;
}

export interface PayoutInfoData {
  tin?: string;
  account_type: string;
  bank_name: string;
  account_number: string;
  account_holder: string;
}

export const vendorService = {
  /**
   * Get current vendor profile
   */
  async getProfile(): Promise<VendorProfile> {
    try {
      const response = await api.get('/vendor/profile');
      return response.data;
    } catch (error: any) {
      const message = error?.response?.data?.detail || 'Failed to fetch vendor profile';
      throw new Error(message);
    }
  },

  /**
   * Save brand info during onboarding
   */
  async saveBrandInfo(data: BrandInfoData): Promise<VendorProfile> {
    try {
      const response = await api.put('/vendor/onboarding/brand-info', data);
      return response.data;
    } catch (error: any) {
      const message = error?.response?.data?.detail || 'Failed to save brand info';
      throw new Error(message);
    }
  },

  /**
   * Save payout info during onboarding
   */
  async savePayoutInfo(data: PayoutInfoData): Promise<VendorProfile> {
    try {
      const response = await api.put('/vendor/onboarding/payout-info', data);
      return response.data;
    } catch (error: any) {
      const message = error?.response?.data?.detail || 'Failed to save payout info';
      throw new Error(message);
    }
  },

  /**
   * Pause vendor store
   */
  async pauseStore(): Promise<VendorProfile> {
    try {
      const response = await api.post('/vendor/store/pause');
      return response.data;
    } catch (error: any) {
      const message = error?.response?.data?.detail || 'Failed to pause store';
      throw new Error(message);
    }
  },

  /**
   * Activate vendor store
   */
  async activateStore(): Promise<VendorProfile> {
    try {
      const response = await api.post('/vendor/store/activate');
      return response.data;
    } catch (error: any) {
      const message = error?.response?.data?.detail || 'Failed to activate store';
      throw new Error(message);
    }
  },

  /**
   * Delete vendor store (soft delete)
   */
  async deleteStore(): Promise<VendorProfile> {
    try {
      const response = await api.delete('/vendor/store');
      return response.data;
    } catch (error: any) {
      const message = error?.response?.data?.detail || 'Failed to delete store';
      throw new Error(message);
    }
  },
};
