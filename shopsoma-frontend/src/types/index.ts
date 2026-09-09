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
  date_of_birth?: string;
  gender?: string;
  email_verified: boolean;
  is_active: boolean;
  profile_image_url?: string;
  is_guest_created?: boolean;
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
  vendor_name?: string | null;
  title: string;
  description?: string;
  size_guide?: SizeGuide | null;
  base_price: number;
  compare_at_price?: number;
  currency: 'NGN' | 'USD';
  category_id?: string | null;
  category_name?: string | null;
  category_parent_name?: string | null;
  collection_id?: string | null;
  collection_name?: string | null;
  inventory_quantity: number;
  total_stock: number;
  status: 'draft' | 'active' | 'inactive' | 'archived';
  is_featured: boolean;
  product_type: 'single' | 'variable';
  made_to_order: boolean;
  made_to_order_timeline?: string;
  care_instructions?: string;
  fabric_composition?: string;
  weight_kg?: number | null;
  length_cm?: number | null;
  width_cm?: number | null;
  height_cm?: number | null;
  moderation_status: 'pending' | 'approved' | 'rejected';
  moderation_notes?: string;
  views_count: number;
  orders_count: number;
  average_rating?: number;
  review_count?: number;
  created_at: string;
  updated_at: string;
  variants?: ProductVariant[];
  variations?: Variation[];
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

// Image upload types
export interface ImageUploadResponse {
  original: string;
  thumbnail?: string;
  medium?: string;
  large?: string;
  s3_key: string;
  uploaded_at: string;
}

export interface ImageBatchUploadResponse {
  images: ImageUploadResponse[];
  total: number;
  success: number;
  failed: number;
}

export interface SizeStock {
  id?: string;
  variation_id?: string;
  size: 'XXS' | 'XS' | 'S' | 'M' | 'L' | 'XL' | 'XXL' | 'XXXL';
  stock: number;
  created_at?: string;
  updated_at?: string;
}

export interface Variation {
  id?: string;
  product_id?: string;
  title: string;
  type?: string;
  color_hex?: string;
  price?: number;
  sale_price?: number;
  images: string[];
  is_active?: boolean;
  size_stocks: SizeStock[];
  created_at?: string;
  updated_at?: string;
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

// Category types
export interface Category {
  id: string;
  name: string;
  slug: string;
  description?: string;
  parent_id?: string | null;
  image_url?: string | null;
  display_order: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

// Collection types
export interface Collection {
  id: string;
  vendor_id: string;
  name: string;
  slug: string;
  description?: string;
  is_active: boolean;
  banner_image_url?: string | null;
  created_at: string;
  updated_at: string;
}

export interface CollectionSummary extends Collection {
  products_available?: number;
  thumbnails?: string[];
}

export interface CollectionDetail extends CollectionSummary {
  description?: string;
}

export interface CollectionProductSummary {
  id: string;
  title: string;
  status: string;
  base_price: number;
  total_stock: number;
  made_to_order: boolean;
  made_to_order_timeline?: string;
  created_at: string;
  image_url?: string | null;
  collection_name?: string | null;
}

export interface CollectionProductsResponse {
  items: CollectionProductSummary[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface CollectionCreate {
  name: string;
  description?: string;
}

// Order types
export type OrderStatus = 'pending' | 'confirmed' | 'processing' | 'shipped' | 'delivered' | 'cancelled' | 'returned';

export interface Order {
  id: string;
  order_number: string;
  customer_id: string;
  vendor_id: string;
  total_amount: number;
  status: OrderStatus;
  order_content: string;
  created_at: string;
  updated_at: string;
  items?: Array<{
    id: string;
    product_title: string;
    quantity: number;
    unit_price: number;
    subtotal: number;
    product_image_url?: string;
    variant_details?: any;
  }>;
}

export interface OrderListResponse {
  orders: Order[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}
