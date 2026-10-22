/**
 * Wishlist Service
 * Handles all wishlist-related API calls
 */
import axios from 'axios';
import { API_BASE_URL, STORAGE_KEYS } from '../config/constants';

const api = axios.create({
  baseURL: API_BASE_URL,
});

// Add auth token to requests
api.interceptors.request.use((config) => {
  const token = localStorage.getItem(STORAGE_KEYS.ACCESS_TOKEN);
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

let refreshPromise: Promise<string> | null = null;

api.interceptors?.response?.use(
  (response) => response,
  async (error) => {
    const originalRequest = error?.config as any;
    if (error?.response?.status === 401 && originalRequest && !originalRequest._retry) {
      const refreshToken = localStorage.getItem(STORAGE_KEYS.REFRESH_TOKEN);
      if (refreshToken) {
        originalRequest._retry = true;
        try {
          if (!refreshPromise) {
            refreshPromise = (async () => {
              try {
                const response = await axios.post(`${API_BASE_URL}/auth/refresh`, {
                  refresh_token: refreshToken,
                });
                const { access_token, refresh_token: nextRefreshToken } = response.data;
                localStorage.setItem(STORAGE_KEYS.ACCESS_TOKEN, access_token);
                if (nextRefreshToken) {
                  localStorage.setItem(STORAGE_KEYS.REFRESH_TOKEN, nextRefreshToken);
                }
                return access_token;
              } finally {
                refreshPromise = null;
              }
            })();
          }
          const newAccessToken = await refreshPromise;
          originalRequest.headers = originalRequest.headers || {};
          originalRequest.headers.Authorization = `Bearer ${newAccessToken}`;
          return api(originalRequest);
        } catch {
          localStorage.removeItem(STORAGE_KEYS.ACCESS_TOKEN);
          localStorage.removeItem(STORAGE_KEYS.REFRESH_TOKEN);
          localStorage.removeItem(STORAGE_KEYS.USER);
        }
      } else {
        localStorage.removeItem(STORAGE_KEYS.ACCESS_TOKEN);
        localStorage.removeItem(STORAGE_KEYS.USER);
      }
    }
    return Promise.reject(error);
  },
);

// Wishlist Types
export interface WishlistItem {
  id: string;
  user_id: string;
  product_id: string;
  created_at: string;
  product_title: string;
  product_price: number;
  product_sale_price?: number;
  product_image?: string;
  product_vendor_name: string;
  product_slug: string;
  is_active: boolean;
}

export interface WishlistResponse {
  items: WishlistItem[];
  total: number;
}

export interface WishlistCheckResponse {
  in_wishlist: boolean;
  wishlist_item_id?: string;
}

/**
 * Wishlist Management
 */
export const wishlistService = {
  // Get user's wishlist
  async getWishlist(): Promise<WishlistResponse> {
    const response = await api.get('/wishlist');
    return response.data;
  },

  // Add product to wishlist
  async addToWishlist(productId: string): Promise<WishlistItem> {
    const response = await api.post('/wishlist', {
      product_id: productId,
    });
    return response.data;
  },

  // Remove product from wishlist
  async removeFromWishlist(productId: string): Promise<void> {
    await api.delete(`/wishlist/${productId}`);
  },

  // Check if product is in wishlist
  async checkInWishlist(productId: string): Promise<WishlistCheckResponse> {
    const response = await api.get(`/wishlist/check/${productId}`);
    return response.data;
  },
};
