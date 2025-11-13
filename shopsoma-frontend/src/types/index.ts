/**
 * Shared TypeScript types for Shopsoma Frontend
 */

// User types
export interface User {
  id: string;
  email: string;
  full_name: string;
  role: 'customer' | 'vendor' | 'admin';
  phone_number?: string;
  email_verified: boolean;
  is_active: boolean;
  last_login_at?: string;
  created_at: string;
}

// Auth types
export interface AuthTokens {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface LoginCredentials {
  email: string;
  password: string;
}

export interface RegisterData {
  email: string;
  password: string;
  full_name: string;
  role: 'customer' | 'vendor';
  phone_number?: string;
}

// Product types
export interface Product {
  id: string;
  vendor_id: string;
  title: string;
  description?: string;
  size_guide?: SizeGuide | null;
  base_price: number;
  compare_at_price?: number;
  category?: string;
  inventory_quantity: number;
  total_stock: number;
  status: 'draft' | 'active' | 'inactive' | 'archived';
  is_featured: boolean;
  moderation_status: 'pending' | 'approved' | 'rejected';
  moderation_notes?: string;
  views_count: number;
  orders_count: number;
  average_rating?: number;
  review_count?: number;
  created_at: string;
  updated_at: string;
  variants?: ProductVariant[];
  images?: ProductImage[];
}

export interface ProductVariant {
  id: string;
  product_id: string;
  size?: string;
  color?: string;
  color_hex?: string;
  price: number;
  compare_at_price?: number;
  stock: number;
  sku?: string;
  is_available: boolean;
}

export interface ProductImage {
  id: string;
  product_id: string;
  image_url: string;
  thumbnail_url?: string;
  alt_text?: string;
  display_order: number;
  is_primary: boolean;
}

export interface SizeGuide {
  title?: string;
  subtitle?: string;
  gender?: string;
  notes?: string;
  rows: SizeGuideRow[];
}

export interface SizeGuideRow {
  label: string;
  standard?: string;
  measurement?: string;
}

// API Response types
export interface ApiError {
  detail: string;
  status_code?: number;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

// Route types
export interface RouteConfig {
  path: string;
  element: React.ReactNode;
  protected?: boolean;
  roles?: ('customer' | 'vendor' | 'admin')[];
  title?: string;
}

// Component prop types
export interface LayoutProps {
  children: React.ReactNode;
}

export interface ErrorBoundaryProps {
  children: React.ReactNode;
  fallback?: React.ReactNode;
}
