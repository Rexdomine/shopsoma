/**
 * Application configuration and constants
 */

// API Configuration
const resolveApiBaseUrl = () => {
  const envUrl = import.meta.env.VITE_API_BASE_URL;
  if (envUrl) {
    return envUrl;
  }

  if (typeof window !== 'undefined') {
    const host = window.location.hostname;
    if (host.includes('shopsoma-staging')) {
      return 'https://shopsoma-staging-api.onrender.com/api/v1';
    }
    if (host.includes('shopsoma')) {
      return 'https://api.shopsoma.com/api/v1';
    }
  }

  return 'http://localhost:8000/api/v1';
};

export const API_BASE_URL = resolveApiBaseUrl();

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
  VENDOR_LOGIN: '/vendor/login',
  VENDOR_SIGNUP: '/vendor/signup',
  VENDOR_SIGNUP_BUSINESS: '/vendor/signup/business-info',
  VENDOR_SIGNUP_THANK_YOU: '/vendor/signup/thank-you',
  VENDOR_OTP: '/vendor/otp',
  VENDOR_SET_PASSWORD: '/vendor/set-password',
  VENDOR_SETTINGS: '/vendor/settings',
  VENDOR_EARNINGS: '/vendor/earnings',
  VENDOR_EXPENSES: '/vendor/earnings/expenses',
  VENDOR_WITHDRAWALS: '/vendor/earnings/withdrawals',
  VENDOR_ANALYTICS: '/vendor/analytics',
  VENDOR_COLLECTIONS: '/vendor/collections',
  VENDOR_BRAND_INFO: '/vendor/settings/brand-info',
  VENDOR_PAYOUT_INFO: '/vendor/settings/payout-information',
  VENDOR_SECURITY: '/vendor/settings/security',
  FORGOT_PASSWORD: '/forgot-password',
  REGISTER: '/register',
  MEN: '/men',
  WOMEN: '/women',
  DESIGNERS: '/designers',
  NEW_ARRIVALS: '/new',
  PERFUMES: '/perfumes',
  BAGS_WALLETS: '/bags-wallets',
  VERIFY_EMAIL: '/verify-email',
  CLAIM_ACCOUNT: '/claim-account',
  PRODUCTS: '/products',
  PRODUCT_DETAIL: '/products/:id',
  CART: '/cart',
  CHECKOUT: '/checkout',
  ORDER_SUCCESS: '/order-success',
  ORDER_TRACKING: '/track/:orderId',
  VENDOR_DASHBOARD: '/vendor/dashboard',
  VENDOR_PRODUCTS: '/vendor/products',
  VENDOR_ORDERS: '/vendor/orders',
  VENDOR_ORDER_DETAIL: '/vendor/orders/:id',
  ADMIN_DASHBOARD: '/admin/dashboard',
  ADMIN_VENDOR_APPLICATIONS: '/admin/vendor-applications',
  ADMIN_VENDORS: '/admin/vendors',
  ADMIN_USERS: '/admin/users',
  ADMIN_PRODUCTS: '/admin/products',
  ADMIN_PRODUCT_DETAIL: '/admin/products/:id',
  ADMIN_PRODUCT_EDIT: '/admin/products/:id/edit',
  ADMIN_PAYOUTS: '/admin/payouts',
  PROFILE: '/profile',
  PROFILE_EDIT: '/profile/edit',
  PROFILE_PASSWORD: '/profile/password',
  PROFILE_ADDRESS: '/profile/address',
  PROFILE_ORDERS: '/profile/orders',
  PROFILE_RETURNS: '/profile/returns',
  PROFILE_WISHLIST: '/profile/wishlist',
  PROFILE_NEWSLETTER: '/profile/newsletter',
  PROFILE_MANAGE_PREFERENCE: '/profile/preferences',
  PROFILE_PAYMENTS: '/profile/payments',
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

// Storefront hero assets
export const MEN_HERO_IMAGE_URL = '/images/hero/men-hero-placeholder.jpg';
export const WOMEN_HERO_IMAGE_URL = '/images/hero/women-hero-placeholder.jpg';
export const VENDOR_LOGIN_IMAGE_URL = '/images/profilebanner.jpg';

// Toast Configuration
export const TOAST_DURATION = 3000;

// Request Timeout
export const REQUEST_TIMEOUT = 30000; // 30 seconds
