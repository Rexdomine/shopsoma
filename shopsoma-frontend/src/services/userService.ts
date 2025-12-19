import api from './api';
import type { User } from '../types';

export interface UpdateProfileData {
  full_name?: string;
  phone_number?: string;
  email?: string;
  date_of_birth?: string;
  gender?: string;
}

export interface ChangePasswordData {
  current_password: string;
  new_password: string;
  confirm_password: string;
}

export interface Address {
  id: string;
  user_id: string;
  full_name: string;
  phone_number: string;
  address_line1: string;
  address_line2?: string;
  city: string;
  state: string;
  postal_code: string;
  country: string;
  is_default: boolean;
  address_type: 'home' | 'work' | 'other';
  created_at: string;
  updated_at: string;
}

export interface CreateAddressData {
  full_name: string;
  phone_number: string;
  address_line1: string;
  address_line2?: string;
  city: string;
  state: string;
  postal_code: string;
  country: string;
  is_default?: boolean;
  address_type?: 'home' | 'work' | 'other';
}

export interface Order {
  id: string;
  order_number: string;
  user_id: string;
  status: 'pending' | 'confirmed' | 'processing' | 'shipped' | 'delivered' | 'cancelled' | 'refunded';
  subtotal: number;
  shipping_cost: number;
  tax: number;
  discount: number;
  total: number;
  payment_method: string;
  payment_status: 'pending' | 'paid' | 'failed' | 'refunded';
  shipping_address: Address;
  tracking_number?: string;
  notes?: string;
  created_at: string;
  updated_at: string;
  items: OrderItem[];
}

export interface OrderItem {
  id: string;
  order_id: string;
  product_id: string;
  variant_id?: string;
  product_title: string;
  variant_details?: string;
  quantity: number;
  price: number;
  subtotal: number;
}

export const userService = {
  // Get current user profile
  async getProfile(): Promise<User> {
    try {
      const response = await api.get('/users/me');
      return response.data;
    } catch (error: any) {
      if (error.response?.status === 401) {
        throw new Error('Please login to view your profile');
      }
      throw new Error('Failed to load profile');
    }
  },

  // Update user profile
  async updateProfile(data: UpdateProfileData): Promise<User> {
    try {
      const response = await api.put('/users/me', data);
      return response.data;
    } catch (error: any) {
      if (error.response?.status === 400) {
        throw new Error(error.response.data?.detail || 'Invalid profile data');
      } else if (error.response?.status === 409) {
        throw new Error('Email is already in use');
      }
      throw new Error('Failed to update profile');
    }
  },

  // Change password
  async changePassword(data: ChangePasswordData): Promise<void> {
    try {
      if (data.new_password !== data.confirm_password) {
        throw new Error('Passwords do not match');
      }

      await api.post('/users/me/change-password', {
        current_password: data.current_password,
        new_password: data.new_password,
      });
    } catch (error: any) {
      if (error.response?.status === 400) {
        throw new Error(error.response.data?.detail || 'Invalid password');
      } else if (error.response?.status === 401) {
        throw new Error('Current password is incorrect');
      } else if (error.message) {
        throw error;
      }
      throw new Error('Failed to change password');
    }
  },

  // Get user addresses
  async getAddresses(): Promise<Address[]> {
    try {
      const response = await api.get('/users/me/addresses');
      return response.data;
    } catch (error: any) {
      if (error.response?.status === 401) {
        throw new Error('Please login to view addresses');
      }
      throw new Error('Failed to load addresses');
    }
  },

  // Create new address
  async createAddress(data: CreateAddressData): Promise<Address> {
    try {
      const response = await api.post('/users/me/addresses', data);
      return response.data;
    } catch (error: any) {
      if (error.response?.status === 400) {
        throw new Error(error.response.data?.detail || 'Invalid address data');
      }
      throw new Error('Failed to create address');
    }
  },

  // Update address
  async updateAddress(addressId: string, data: Partial<CreateAddressData>): Promise<Address> {
    try {
      const response = await api.put(`/users/me/addresses/${addressId}`, data);
      return response.data;
    } catch (error: any) {
      if (error.response?.status === 400) {
        throw new Error(error.response.data?.detail || 'Invalid address data');
      } else if (error.response?.status === 404) {
        throw new Error('Address not found');
      }
      throw new Error('Failed to update address');
    }
  },

  // Delete address
  async deleteAddress(addressId: string): Promise<void> {
    try {
      await api.delete(`/users/me/addresses/${addressId}`);
    } catch (error: any) {
      if (error.response?.status === 404) {
        throw new Error('Address not found');
      } else if (error.response?.status === 400) {
        throw new Error('Cannot delete default address. Set another address as default first');
      }
      throw new Error('Failed to delete address');
    }
  },

  // Set default address
  async setDefaultAddress(addressId: string): Promise<Address> {
    try {
      const response = await api.put(`/users/me/addresses/${addressId}`, { is_default: true });
      return response.data;
    } catch (error: any) {
      if (error.response?.status === 404) {
        throw new Error('Address not found');
      }
      throw new Error('Failed to set default address');
    }
  },

  // Get user orders
  async getOrders(page: number = 1, pageSize: number = 10): Promise<{ orders: Order[]; total: number }> {
    try {
      const response = await api.get('/users/me/orders', {
        params: { page, page_size: pageSize },
      });
      return {
        orders: response.data.items || response.data,
        total: response.data.total || response.data.length,
      };
    } catch (error: any) {
      if (error.response?.status === 401) {
        throw new Error('Please login to view orders');
      }
      throw new Error('Failed to load orders');
    }
  },

  // Get single order details
  async getOrder(orderId: string): Promise<Order> {
    try {
      const response = await api.get(`/users/me/orders/${orderId}`);
      return response.data;
    } catch (error: any) {
      if (error.response?.status === 404) {
        throw new Error('Order not found');
      } else if (error.response?.status === 401) {
        throw new Error('Please login to view order');
      }
      throw new Error('Failed to load order');
    }
  },

  // Cancel order
  async cancelOrder(orderId: string, reason?: string): Promise<Order> {
    try {
      const response = await api.post(`/users/me/orders/${orderId}/cancel`, { reason });
      return response.data;
    } catch (error: any) {
      if (error.response?.status === 404) {
        throw new Error('Order not found');
      } else if (error.response?.status === 400) {
        throw new Error(error.response.data?.detail || 'Cannot cancel this order');
      }
      throw new Error('Failed to cancel order');
    }
  },
};
