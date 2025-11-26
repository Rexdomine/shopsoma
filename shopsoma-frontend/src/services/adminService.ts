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

  // Get admin dashboard statistics
  async getStats(): Promise<AdminStats> {
    const response = await api.get('/admin/stats');
    return response.data;
  },
};
