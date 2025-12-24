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

export interface VendorEarningsSummary {
  current_earnings: number;
  projected_earnings: number;
  expenses: number;
  current_earnings_change_pct?: number | null;
  projected_earnings_change_pct?: number | null;
  expenses_change_pct?: number | null;
  start_date?: string | null;
  end_date?: string | null;
}

export interface VendorAnalyticsSummary {
  total_revenue: number;
  revenue_change_pct?: number | null;
  commission_rate_pct?: number | null;
  start_date?: string | null;
  end_date?: string | null;
}

export interface VendorAnalyticsChartPoint {
  timestamp: string;
  revenue: number;
  expenses: number;
}

export interface VendorAnalyticsChartResponse {
  range: string;
  start_date: string;
  end_date: string;
  points: VendorAnalyticsChartPoint[];
}

export interface VendorAnalyticsStats {
  total_products_sold: number;
  wishlisted_products: number;
  returning_customers: number;
  new_customers: number;
}
export interface VendorPayoutSummary {
  current_earnings: number;
  pending_amount: number;
  available_payout: number;
  last_payout_amount: number;
  last_payout_date: string | null;
  total_earnings: number;
  current_month_sales: number;
}

export interface VendorPayoutRequest {
  amount: number;
  payment_method_id?: string;
}

export interface VendorPayout {
  id: string;
  vendor_id: string;
  payout_period_start: string;
  payout_period_end: string;
  total_sales: number;
  commission_amount: number;
  payout_amount: number;
  status: string;
  processed_at: string | null;
  payment_reference: string | null;
  notes: string | null;
  created_at: string;
}

export interface VendorPayoutListResponse {
  payouts: VendorPayout[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

const extractErrorMessage = (error: any, fallback: string) => {
  if (error?.code === 'ECONNABORTED') {
    return 'Request timed out. Please try again.';
  }
  if (typeof error?.message === 'string' && error.message.toLowerCase().includes('timeout')) {
    return 'Request timed out. Please try again.';
  }
  const detail = error?.response?.data?.detail;
  if (typeof detail === 'string') {
    return detail;
  }
  if (detail && typeof detail === 'object') {
    if (typeof detail.message === 'string') {
      return detail.message;
    }
    return JSON.stringify(detail);
  }
  return error?.message || fallback;
};

export type EarningsViewMode = 'products' | 'orders';

export interface VendorEarningsProductRow {
  id: string;
  order_id: string;
  product_id: string;
  order_number: string;
  product_title: string;
  product_image_url?: string | null;
  unit_price: number;
  quantity: number;
  commission_amount: number;
  vendor_payout: number;
  payout_status?: string | null;
  status: string;
  delivered_at: string | null;
  withdraw_available?: boolean;
  withdraw_days_left?: number | null;
  withdraw_available_at?: string | null;
}

export interface VendorEarningsOrderRow {
  id: string;
  order_number: string;
  items: string[];
  total_quantity: number;
  total_commission: number;
  total_payout: number;
  status: string;
  delivered_at: string | null;
  payout_status?: string | null;
  withdraw_available?: boolean;
  withdraw_days_left?: number | null;
  withdraw_available_at?: string | null;
}

export interface VendorEarningsItemsResponse<TItem> {
  view: EarningsViewMode;
  items: TItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
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

  async getEarningsSummary(params?: {
    start_date?: string;
    end_date?: string;
  }): Promise<VendorEarningsSummary> {
    try {
      const response = await api.get('/vendor/earnings/summary', { params });
      return response.data;
    } catch (error: any) {
      const message = error?.response?.data?.detail || 'Failed to fetch earnings summary';
      throw new Error(message);
    }
  },

  async getEarningsItems(params: {
    view?: EarningsViewMode;
    page?: number;
    page_size?: number;
    start_date?: string;
    end_date?: string;
    search?: string;
  }): Promise<VendorEarningsItemsResponse<VendorEarningsProductRow | VendorEarningsOrderRow>> {
    try {
      const response = await api.get('/vendor/earnings/items', { params });
      return response.data;
    } catch (error: any) {
      const message = error?.response?.data?.detail || 'Failed to fetch earnings items';
      throw new Error(message);
    }
  },

  async getAnalyticsSummary(params?: {
    start_date?: string;
    end_date?: string;
  }): Promise<VendorAnalyticsSummary> {
    try {
      const response = await api.get('/vendor/analytics/summary', { params });
      return response.data;
    } catch (error: any) {
      const message = error?.response?.data?.detail || 'Failed to fetch analytics summary';
      throw new Error(message);
    }
  },

  async getAnalyticsChart(params?: {
    range?: string;
    start_date?: string;
    end_date?: string;
  }): Promise<VendorAnalyticsChartResponse> {
    try {
      const response = await api.get('/vendor/analytics/chart', { params });
      return response.data;
    } catch (error: any) {
      const message = error?.response?.data?.detail || 'Failed to fetch analytics chart';
      throw new Error(message);
    }
  },

  async getAnalyticsStats(params?: {
    start_date?: string;
    end_date?: string;
  }): Promise<VendorAnalyticsStats> {
    try {
      const response = await api.get('/vendor/analytics/stats', { params });
      return response.data;
    } catch (error: any) {
      const message = error?.response?.data?.detail || 'Failed to fetch analytics stats';
      throw new Error(message);
    }
  },
  async getPayoutSummary(): Promise<VendorPayoutSummary> {
    try {
      const response = await api.get('/vendor/payouts/summary', { timeout: 30000 });
      return response.data;
    } catch (error: any) {
      const message = extractErrorMessage(error, 'Failed to fetch payout summary');
      throw new Error(message);
    }
  },

  async requestPayout(data: VendorPayoutRequest) {
    try {
      const response = await api.post('/vendor/payouts/request', data);
      return response.data;
    } catch (error: any) {
      const message = extractErrorMessage(error, 'Failed to request payout');
      throw new Error(message);
    }
  },

  async listPayouts(params?: {
    page?: number;
    page_size?: number;
    start_date?: string;
    end_date?: string;
    status?: string;
    search?: string;
  }): Promise<VendorPayoutListResponse> {
    try {
      const response = await api.get('/vendor/payouts', { params });
      return response.data;
    } catch (error: any) {
      const message = extractErrorMessage(error, 'Failed to fetch payouts');
      throw new Error(message);
    }
  },

  async getPayout(payoutId: string): Promise<VendorPayout> {
    try {
      const response = await api.get(`/vendor/payouts/${payoutId}`);
      return response.data;
    } catch (error: any) {
      const message = extractErrorMessage(error, 'Failed to fetch payout');
      throw new Error(message);
    }
  },

  async cancelPayout(payoutId: string): Promise<VendorPayout> {
    try {
      const response = await api.post(`/vendor/payouts/${payoutId}/cancel`);
      return response.data;
    } catch (error: any) {
      const message = extractErrorMessage(error, 'Failed to cancel payout');
      throw new Error(message);
    }
  },
};
