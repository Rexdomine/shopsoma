import api from './api';

export type AdminPayoutStatus = 'pending' | 'processing' | 'completed' | 'failed';

export interface AdminPayoutVendor {
  id: string;
  business_name: string;
  email?: string | null;
  phone?: string | null;
}

export interface AdminPayout {
  id: string;
  vendor: AdminPayoutVendor;
  payout_period_start: string;
  payout_period_end: string;
  total_sales: number;
  commission_amount: number;
  payout_amount: number;
  status: AdminPayoutStatus;
  processed_at?: string | null;
  payment_reference?: string | null;
  notes?: string | null;
  created_at: string;
}

export interface AdminPayoutListResponse {
  payouts: AdminPayout[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface AdminPayoutListParams {
  page?: number;
  page_size?: number;
  status?: AdminPayoutStatus;
  vendor_id?: string;
  start_date?: string;
  end_date?: string;
  search?: string;
}

export interface AdminPayoutStatusUpdate {
  status: AdminPayoutStatus;
  payment_reference?: string;
  notes?: string;
}

export interface AdminPayoutBulkStatusUpdate {
  payout_ids: string[];
  status: AdminPayoutStatus;
  notes?: string;
}

export const adminPayoutService = {
  async listPayouts(params?: AdminPayoutListParams): Promise<AdminPayoutListResponse> {
    const searchParams = new URLSearchParams();

    if (params?.page) searchParams.append('page', params.page.toString());
    if (params?.page_size) searchParams.append('page_size', params.page_size.toString());
    if (params?.status) searchParams.append('status', params.status);
    if (params?.vendor_id) searchParams.append('vendor_id', params.vendor_id);
    if (params?.start_date) searchParams.append('start_date', params.start_date);
    if (params?.end_date) searchParams.append('end_date', params.end_date);
    if (params?.search) searchParams.append('search', params.search);

    const response = await api.get(`/admin/payouts?${searchParams.toString()}`);
    return response.data;
  },

  async updatePayoutStatus(payoutId: string, payload: AdminPayoutStatusUpdate): Promise<AdminPayout> {
    const response = await api.patch(`/admin/payouts/${payoutId}/status`, payload);
    return response.data;
  },

  async bulkUpdateStatus(payload: AdminPayoutBulkStatusUpdate): Promise<{ success: boolean; updated_count: number; message: string }> {
    const response = await api.patch('/admin/payouts/bulk/status', payload);
    return response.data;
  },

  async exportPayoutsCSV(params?: AdminPayoutListParams): Promise<Blob> {
    const response = await api.get('/admin/payouts/export/csv', {
      params,
      responseType: 'blob',
    });
    return response.data;
  },
};

export const downloadCSV = (blob: Blob, filename: string = 'payouts.csv') => {
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.URL.revokeObjectURL(url);
};
