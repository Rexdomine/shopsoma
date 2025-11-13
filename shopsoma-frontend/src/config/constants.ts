/**
 * Application configuration and constants
 */

// API Configuration
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1';

// App Configuration
export const APP_NAME = 'Shopsoma';
export const APP_VERSION = '1.0.0';
export const APP_DESCRIPTION = 'Multi-vendor marketplace for African fashion';

// Storage Keys
export const STORAGE_KEYS = {
  ACCESS_TOKEN: 'shopsoma_access_token',
  REFRESH_TOKEN: 'shopsoma_refresh_token',
  USER: 'shopsoma_user',
  THEME: 'shopsoma_theme',
} as const;

// Route Paths
export const ROUTES = {
  HOME: '/',
  LOGIN: '/login',
  REGISTER: '/register',
  PRODUCTS: '/products',
  PRODUCT_DETAIL: '/products/:id',
  CART: '/cart',
  CHECKOUT: '/checkout',
  VENDOR_DASHBOARD: '/vendor/dashboard',
  VENDOR_PRODUCTS: '/vendor/products',
  VENDOR_ORDERS: '/vendor/orders',
  ADMIN_DASHBOARD: '/admin/dashboard',
  ADMIN_VENDORS: '/admin/vendors',
  ADMIN_PRODUCTS: '/admin/products',
  PROFILE: '/profile',
  ORDERS: '/orders',
  NOT_FOUND: '/404',
  SERVER_ERROR: '/500',
} as const;

// Pagination
export const PAGINATION = {
  DEFAULT_PAGE: 1,
  DEFAULT_PAGE_SIZE: 20,
  MAX_PAGE_SIZE: 100,
} as const;

// Image Configuration
export const IMAGE_CONFIG = {
  MAX_SIZE_MB: 10,
  ALLOWED_TYPES: ['image/jpeg', 'image/png', 'image/webp', 'image/gif'],
  PLACEHOLDER: '/images/placeholder-product.svg',
} as const;

// Toast Configuration
export const TOAST_DURATION = 3000;

// Request Timeout
export const REQUEST_TIMEOUT = 30000; // 30 seconds
