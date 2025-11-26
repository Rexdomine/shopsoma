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
  date_of_birth?: string;
  gender?: string;
  role?: 'customer' | 'vendor';
}

export interface LoginResponse {
  user: User;
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface EmailStatusResponse {
  email: string;
  exists: boolean;
  has_password: boolean;
  is_guest_created: boolean;
  is_active: boolean;
  can_claim: boolean;
}

export interface ClaimAccountPayload {
  email: string;
  password: string;
  token: string;
  full_name?: string;
}

export const authService = {
  // Login user
  async login(credentials: LoginCredentials): Promise<LoginResponse> {
    try {
      const response = await api.post('/auth/login', {
        email: credentials.email,
        password: credentials.password,
      });

      // Store tokens
      const { access_token, refresh_token } = response.data;
      localStorage.setItem(STORAGE_KEYS.ACCESS_TOKEN, access_token);
      localStorage.setItem(STORAGE_KEYS.REFRESH_TOKEN, refresh_token);

      // Get user info and store
      const userResponse = await api.get('/auth/me');
      localStorage.setItem(STORAGE_KEYS.USER, JSON.stringify(userResponse.data));

      return {
        user: userResponse.data,
        access_token,
        refresh_token,
        token_type: response.data.token_type,
        expires_in: response.data.expires_in,
      };
    } catch (error: any) {
      // Enhanced error handling
      if (error.response?.status === 401) {
        throw new Error('Invalid email or password');
      } else if (error.response?.status === 403) {
        throw new Error('Your account has been disabled');
      } else if (error.response?.status === 429) {
        throw new Error('Too many login attempts. Please try again later');
      } else if (error.response?.data?.detail) {
        throw new Error(error.response.data.detail);
      }
      throw new Error('Login failed. Please try again');
    }
  },

  // Register new user
  async register(data: RegisterData): Promise<LoginResponse> {
    try {
      // First create the user
      const signupResponse = await api.post('/auth/signup', {
        email: data.email,
        password: data.password,
        full_name: data.full_name,
        phone_number: data.phone_number,
        date_of_birth: data.date_of_birth,
        gender: data.gender,
        role: data.role || 'customer',
      });

      // Then login to get tokens
      const loginResponse = await api.post('/auth/login', {
        email: data.email,
        password: data.password,
      });

      // Store tokens
      const { access_token, refresh_token } = loginResponse.data;
      localStorage.setItem(STORAGE_KEYS.ACCESS_TOKEN, access_token);
      localStorage.setItem(STORAGE_KEYS.REFRESH_TOKEN, refresh_token);
      localStorage.setItem(STORAGE_KEYS.USER, JSON.stringify(signupResponse.data));

      return {
        user: signupResponse.data,
        access_token,
        refresh_token,
        token_type: loginResponse.data.token_type,
        expires_in: loginResponse.data.expires_in,
      };
    } catch (error: any) {
      // Enhanced error handling
      if (error.response?.status === 400) {
        if (error.response.data?.detail?.includes('Email already registered')) {
          throw new Error('This email is already registered');
        }
        throw new Error(error.response.data?.detail || 'Invalid registration data');
      } else if (error.response?.data?.detail) {
        throw new Error(error.response.data.detail);
      }
      throw new Error('Registration failed. Please try again');
    }
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

  async checkEmailStatus(email: string): Promise<EmailStatusResponse> {
    try {
      const response = await api.post('/auth/email-status', { email });
      return response.data;
    } catch (error: any) {
      throw new Error(error?.response?.data?.detail || 'Unable to verify email.');
    }
  },

  async requestAccountClaimEmail(email: string): Promise<void> {
    try {
      await api.post('/auth/claim-account/request', { email });
    } catch (error: any) {
      if (error?.response?.status === 404) {
        throw new Error('No account found for this email.');
      }
      if (error?.response?.status === 400) {
        throw new Error(error?.response?.data?.detail || 'Account already claimed.');
      }
      throw new Error('Unable to send claim email. Please try again.');
    }
  },

  async claimAccount(payload: ClaimAccountPayload): Promise<User> {
    try {
      const response = await api.post('/auth/claim-account', payload);
      const { access_token, refresh_token } = response.data;
      localStorage.setItem(STORAGE_KEYS.ACCESS_TOKEN, access_token);
      if (refresh_token) {
        localStorage.setItem(STORAGE_KEYS.REFRESH_TOKEN, refresh_token);
      }
      const userResponse = await api.get('/auth/me');
      localStorage.setItem(STORAGE_KEYS.USER, JSON.stringify(userResponse.data));
      return userResponse.data;
    } catch (error: any) {
      if (error?.response?.status === 400 || error?.response?.status === 404) {
        throw new Error(error?.response?.data?.detail || 'Unable to claim account.');
      }
      throw new Error('Unable to claim account. Please try again.');
    }
  },
};
