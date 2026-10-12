import axios from 'axios';
import type { AxiosInstance, AxiosError } from 'axios';
import { API_BASE_URL, STORAGE_KEYS } from '../config/constants';

const clearStoredAuthSession = () => {
  localStorage.removeItem(STORAGE_KEYS.ACCESS_TOKEN);
  localStorage.removeItem(STORAGE_KEYS.REFRESH_TOKEN);
  localStorage.removeItem(STORAGE_KEYS.USER);
};

const isAuthEndpoint = (url?: string): boolean => {
  if (!url) return false;
  return [
    '/auth/login',
    '/auth/signup',
    '/auth/refresh',
    '/auth/forgot-password',
    '/auth/reset-password',
    '/auth/verify-email',
    '/auth/claim',
  ].some((path) => url.includes(path));
};

const handleAuthExpired = () => {
  clearStoredAuthSession();
  if (typeof window !== 'undefined') {
    const pathname = window.location.pathname;
    const isAlreadyOnAuthPage =
      pathname === '/login' ||
      pathname === '/vendor/login' ||
      pathname === '/register' ||
      pathname === '/vendor/signup' ||
      pathname.startsWith('/vendor/signup') ||
      pathname === '/forgot-password' ||
      pathname === '/reset-password' ||
      pathname === '/verify-email' ||
      pathname === '/claim-account' ||
      pathname === '/vendor/otp' ||
      pathname === '/vendor/set-password';

    if (!isAlreadyOnAuthPage) {
      const isVendorRoute = pathname.startsWith('/vendor');
      window.location.href = isVendorRoute ? '/vendor/login' : '/login';
    }
  }
};

// Create axios instance
const api: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 10000,
});

// Request interceptor to add auth token
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem(STORAGE_KEYS.ACCESS_TOKEN);
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

let refreshPromise: Promise<string> | null = null;

// Response interceptor for error handling
api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as any;

    // Do not attempt token refresh for unauthenticated auth endpoints (login, signup, etc.)
    if (isAuthEndpoint(originalRequest?.url)) {
      return Promise.reject(error);
    }

    // Handle 401 Unauthorized - token expired
    if (error.response?.status === 401) {
      // If this request was already retried with a refreshed token and still failed 401, session has expired
      if (originalRequest?._retry) {
        handleAuthExpired();
        return Promise.reject(error);
      }

      const refreshToken = localStorage.getItem(STORAGE_KEYS.REFRESH_TOKEN);
      if (!refreshToken) {
        // No refresh token available, session has expired -> redirect to login
        handleAuthExpired();
        return Promise.reject(error);
      }

      originalRequest._retry = true;

      try {
        if (!refreshPromise) {
          refreshPromise = (async () => {
            try {
              const response = await axios.post(`${API_BASE_URL}/auth/refresh`, {
                refresh_token: refreshToken,
              });

              const { access_token } = response.data;
              localStorage.setItem(STORAGE_KEYS.ACCESS_TOKEN, access_token);
              return access_token;
            } finally {
              refreshPromise = null;
            }
          })();
        }

        const newAccessToken = await refreshPromise;

        // Retry the original request with new token
        originalRequest.headers.Authorization = `Bearer ${newAccessToken}`;
        return api(originalRequest);
      } catch (refreshError) {
        // Refresh failed, logout user
        handleAuthExpired();
        return Promise.reject(refreshError);
      }
    }

    return Promise.reject(error);
  }
);

export default api;
