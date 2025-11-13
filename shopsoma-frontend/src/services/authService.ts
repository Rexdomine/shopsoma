import api from './api';
import type { User, AuthTokens } from '../types';
import { STORAGE_KEYS } from '../config/constants';

export interface LoginCredentials {
  email: string;
  password: string;
}

export interface RegisterData {
  email: string;
  password: string;
  full_name: string;
  phone_number?: string;
  role?: 'customer' | 'vendor';
}

export interface LoginResponse {
  user: User;
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export const authService = {
  // Login user
  async login(credentials: LoginCredentials): Promise<LoginResponse> {
    const formData = new FormData();
    formData.append('username', credentials.email);
    formData.append('password', credentials.password);

    const response = await api.post('/auth/login', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });

    // Store tokens
    const { access_token, refresh_token } = response.data;
    localStorage.setItem(STORAGE_KEYS.ACCESS_TOKEN, access_token);
    localStorage.setItem(STORAGE_KEYS.REFRESH_TOKEN, refresh_token);

    return response.data;
  },

  // Register new user
  async register(data: RegisterData): Promise<LoginResponse> {
    const response = await api.post('/auth/register', data);

    // Store tokens
    const { access_token, refresh_token } = response.data;
    localStorage.setItem(STORAGE_KEYS.ACCESS_TOKEN, access_token);
    localStorage.setItem(STORAGE_KEYS.REFRESH_TOKEN, refresh_token);

    return response.data;
  },

  // Logout user
  async logout(): Promise<void> {
    try {
      await api.post('/auth/logout');
    } finally {
      // Clear local storage regardless of API response
      localStorage.removeItem(STORAGE_KEYS.ACCESS_TOKEN);
      localStorage.removeItem(STORAGE_KEYS.REFRESH_TOKEN);
      localStorage.removeItem(STORAGE_KEYS.USER);
    }
  },

  // Get current user profile
  async getCurrentUser(): Promise<User> {
    const response = await api.get('/auth/me');
    return response.data;
  },

  // Refresh access token
  async refreshToken(refreshToken: string): Promise<AuthTokens> {
    const response = await api.post('/auth/refresh', {
      refresh_token: refreshToken,
    });
    return response.data;
  },

  // Request password reset
  async requestPasswordReset(email: string): Promise<void> {
    await api.post('/auth/password-reset/request', { email });
  },

  // Reset password with token
  async resetPassword(token: string, newPassword: string): Promise<void> {
    await api.post('/auth/password-reset/confirm', {
      token,
      new_password: newPassword,
    });
  },

  // Verify email
  async verifyEmail(token: string): Promise<void> {
    await api.post('/auth/verify-email', { token });
  },
};
