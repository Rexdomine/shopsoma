import api from './api';

export type ReturnStatus = 'requested' | 'approved' | 'rejected' | 'received' | 'refunded';

export interface AdminReturnCustomer {
  id: string;
  full_name: string;
  email: string;
}

export interface AdminReturnListItem {
  id: string;
  return_number: string;
  status: ReturnStatus;
  reason: string;
  created_at: string;
  order_number?: string;
  customer?: AdminReturnCustomer;
  product_title?: string;
  quantity?: number;
  amount?: number;
}

export interface AdminReturnListResponse {
  returns: AdminReturnListItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface AdminReturnDetail {
  id: string;
  return_number: string;
  status: ReturnStatus;
  reason: string;
  description?: string;
  opened?: string;
  return_action?: string;
  admin_notes?: string;
  rejection_reason?: string;
  refund_amount?: number;
  refund_method?: string;
  approved_by?: string;
  approved_at?: string;
  created_at: string;
  updated_at: string;
  order_id: string;
  order_number?: string;
  order_date?: string;
  product_title?: string;
  quantity?: number;
  amount?: number;
  product_image_url?: string;
}

export interface AdminReturnFilters {
  page?: number;
  page_size?: number;
  status?: ReturnStatus;
  search?: string;
  date_from?: string;
  date_to?: string;
}

export interface AdminReturnStatusUpdate {
  status: ReturnStatus;
  admin_notes?: string;
  rejection_reason?: string;
  refund_amount?: number;
  refund_method?: string;
}

export interface AdminReturnNotesUpdate {
  admin_notes?: string;
}

export const listAdminReturns = async (params?: AdminReturnFilters): Promise<AdminReturnListResponse> => {
  const response = await api.get<AdminReturnListResponse>('/admin/returns', { params });
  return response.data;
};

export const getAdminReturn = async (returnId: string): Promise<AdminReturnDetail> => {
  const response = await api.get<AdminReturnDetail>(`/admin/returns/${returnId}`);
  return response.data;
};

export const updateAdminReturnStatus = async (
  returnId: string,
  data: AdminReturnStatusUpdate
): Promise<AdminReturnDetail> => {
  const response = await api.patch<AdminReturnDetail>(`/admin/returns/${returnId}/status`, data);
  return response.data;
};

export const updateAdminReturnNotes = async (
  returnId: string,
  data: AdminReturnNotesUpdate
): Promise<AdminReturnDetail> => {
  const response = await api.patch<AdminReturnDetail>(`/admin/returns/${returnId}/notes`, data);
  return response.data;
};
