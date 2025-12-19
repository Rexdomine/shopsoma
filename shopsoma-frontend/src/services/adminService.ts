import api from './api';
import type { User, PaginatedResponse } from '../types';

export interface UserListItem extends User {
  created_at: string;
  last_login?: string;
}

export interface UserListFilters {
  page?: number;
  page_size?: number;
  search?: string;
  role?: 'customer' | 'vendor' | 'admin';
  is_active?: boolean;
}

export interface AdminStats {
  total_users: number;
  active_users: number;
  inactive_users: number;
  verified_emails: number;
  role_breakdown: {
    customer: number;
    vendor: number;
    admin: number;
  };
}

export interface VendorListItem {
  id: string;
  user_id: string;
  business_name: string;
  business_description?: string;
  business_address?: string;
  business_phone?: string;
  email: string;
  full_name: string;
  approved: boolean;
  approved_at?: string;
  kyc_status?: string;
  kyc_submitted_at?: string;
  commission_rate: number;
  is_active: boolean;
  is_onboarding: boolean;
  brand_info_completed: boolean;
  payout_info_completed: boolean;
  total_products: number;
  total_orders: number;
  total_revenue: number;
  created_at: string;
  store_active?: boolean;
  store_paused_at?: string;
  store_deleted_at?: string;
}

export interface VendorListFilters {
  page?: number;
  page_size?: number;
  search?: string;
  approved?: boolean;
  kyc_status?: string;
  is_active?: boolean;
}

export interface VendorApplication {
  id: string;
  first_name: string;
  last_name: string;
  email: string;
  phone_country_code: string;
  phone_number: string;
  business_name: string;
  business_location: string;
  is_business_registered: boolean;
  product_categories: string[];
  local_production_level: string;
  years_in_business: string;
  brand_story?: string;
  website_link?: string;
  social_media_handles?: any;
  status: string;
  admin_notes?: string;
  vendor_id?: string;
  created_at: string;
  reviewed_at?: string;
}

export interface VendorApplicationFilters {
  page?: number;
  page_size?: number;
  status?: string;
  search?: string;
}

export const adminService = {
  // List all users with pagination and filters
  async listUsers(filters?: UserListFilters): Promise<PaginatedResponse<UserListItem>> {
    const params = new URLSearchParams();

    if (filters?.page) params.append('page', filters.page.toString());
    if (filters?.page_size) params.append('page_size', filters.page_size.toString());
    if (filters?.search) params.append('search', filters.search);
    if (filters?.role) params.append('role', filters.role);
    if (filters?.is_active !== undefined) params.append('is_active', filters.is_active.toString());

    const response = await api.get(`/admin/users?${params.toString()}`);
    return response.data;
  },

  // Get detailed user information
  async getUser(userId: string): Promise<User> {
    const response = await api.get(`/admin/users/${userId}`);
    return response.data;
  },

  // Update user information
  async updateUser(userId: string, data: Partial<User>): Promise<User> {
    const response = await api.put(`/admin/users/${userId}`, data);
    return response.data;
  },

  // Toggle user active status
  async toggleUserStatus(userId: string, isActive: boolean): Promise<void> {
    await api.put(`/admin/users/${userId}/status?is_active=${isActive}`);
  },

  // Delete user (hard delete - for testing only)
  async deleteUser(userId: string): Promise<void> {
    await api.delete(`/admin/users/${userId}`);
  },

  // Reset user password (admin only)
  async resetUserPassword(userId: string, newPassword: string): Promise<void> {
    await api.post(`/admin/users/${userId}/reset-password`, {
      new_password: newPassword
    });
  },

  // Get admin dashboard statistics
  async getStats(): Promise<AdminStats> {
    const response = await api.get('/admin/stats');
    return response.data;
  },

  // ==================== VENDOR MANAGEMENT ====================

  // List all vendors with pagination and filters
  async listVendors(filters?: VendorListFilters): Promise<PaginatedResponse<VendorListItem>> {
    const params = new URLSearchParams();

    if (filters?.page) params.append('page', filters.page.toString());
    if (filters?.page_size) params.append('page_size', filters.page_size.toString());
    if (filters?.search) params.append('search', filters.search);
    if (filters?.approved !== undefined) params.append('approved', filters.approved.toString());
    if (filters?.kyc_status) params.append('kyc_status', filters.kyc_status);
    if (filters?.is_active !== undefined) params.append('is_active', filters.is_active.toString());

    const response = await api.get(`/admin/vendors?${params.toString()}`);
    return response.data;
  },

  // Get detailed vendor information
  async getVendor(vendorId: string): Promise<any> {
    const response = await api.get(`/admin/vendors/${vendorId}`);
    return response.data;
  },

  // Update vendor commission rate
  async updateVendorCommission(vendorId: string, commissionRate: number): Promise<void> {
    await api.put(`/admin/vendors/${vendorId}/commission?commission_rate=${commissionRate}`);
  },

  // Approve vendor account
  async approveVendor(vendorId: string): Promise<void> {
    await api.put(`/admin/vendors/${vendorId}/approve`);
  },

  // Approve vendor KYC
  async approveVendorKYC(vendorId: string): Promise<void> {
    await api.put(`/admin/vendors/${vendorId}/kyc/approve`);
  },

  // Reject vendor KYC
  async rejectVendorKYC(vendorId: string, reason: string): Promise<void> {
    await api.put(`/admin/vendors/${vendorId}/kyc/reject?reason=${encodeURIComponent(reason)}`);
  },

  // Restore deleted vendor store
  async restoreVendorStore(vendorId: string): Promise<any> {
    const response = await api.post(`/admin/vendors/${vendorId}/restore`);
    return response.data;
  },

  // ==================== VENDOR APPLICATIONS ====================

  // List vendor applications
  async listVendorApplications(filters?: VendorApplicationFilters): Promise<PaginatedResponse<VendorApplication>> {
    const params = new URLSearchParams();

    if (filters?.page) params.append('page', filters.page.toString());
    if (filters?.page_size) params.append('page_size', filters.page_size.toString());
    if (filters?.status) params.append('status', filters.status);
    if (filters?.search) params.append('search', filters.search);

    const response = await api.get(`/admin/vendor-applications?${params.toString()}`);
    return response.data;
  },

  // Get detailed vendor application
  async getVendorApplication(applicationId: string): Promise<VendorApplication> {
    const response = await api.get(`/admin/vendor-applications/${applicationId}`);
    return response.data;
  },

  // Update application notes
  async updateApplicationNotes(applicationId: string, notes: string): Promise<void> {
    await api.put(`/admin/vendor-applications/${applicationId}/notes?admin_notes=${encodeURIComponent(notes)}`);
  },

  // Approve vendor application (uses the existing endpoint from vendor_applications.py)
  async approveVendorApplication(applicationId: string, adminNotes?: string): Promise<void> {
    await api.post(`/vendor-applications/${applicationId}/approve`, {
      status: 'approved',
      admin_notes: adminNotes || '',
    });
  },

  // Reject vendor application
  async rejectVendorApplication(applicationId: string, adminNotes?: string): Promise<void> {
    await api.post(`/vendor-applications/${applicationId}/reject`, {
      status: 'rejected',
      admin_notes: adminNotes || '',
    });
  },

  // Delete vendor application (for testing/cleanup)
  async deleteVendorApplication(applicationId: string): Promise<void> {
    await api.delete(`/vendor-applications/${applicationId}`);
  },

  // ==================== PRODUCT MANAGEMENT ====================

  // List all products with pagination and filters
  async listProducts(filters?: {
    page?: number;
    page_size?: number;
    search?: string;
    status?: 'draft' | 'active' | 'inactive' | 'archived';
    moderation_status?: 'pending' | 'approved' | 'rejected';
    vendor_id?: string;
    category_id?: string;
    is_featured?: boolean;
  }): Promise<PaginatedResponse<any>> {
    const params = new URLSearchParams();

    if (filters?.page) params.append('page', filters.page.toString());
    if (filters?.page_size) params.append('page_size', filters.page_size.toString());
    if (filters?.search) params.append('search', filters.search);
    if (filters?.status) params.append('status', filters.status);
    if (filters?.moderation_status) params.append('moderation_status', filters.moderation_status);
    if (filters?.vendor_id) params.append('vendor_id', filters.vendor_id);
    if (filters?.category_id) params.append('category_id', filters.category_id);
    if (filters?.is_featured !== undefined) params.append('is_featured', filters.is_featured.toString());

    const response = await api.get(`/admin/products?${params.toString()}`);
    return response.data;
  },

  // Approve a product
  async approveProduct(productId: string, notes?: string): Promise<any> {
    const response = await api.put(`/admin/products/${productId}/approve`, {
      notes: notes || null
    });
    return response.data;
  },

  // Reject a product
  async rejectProduct(productId: string, reason: string, notes?: string): Promise<any> {
    const response = await api.put(`/admin/products/${productId}/reject`, {
      reason,
      notes: notes || null
    });
    return response.data;
  },

  // Delete a product (permanently remove from marketplace)
  async deleteProduct(productId: string): Promise<void> {
    await api.delete(`/admin/products/${productId}`);
  },
};
