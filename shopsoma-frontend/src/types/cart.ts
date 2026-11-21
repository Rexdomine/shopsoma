import type { Product, ProductVariant } from './index';

export interface CartItem {
  id: string; // Unique cart item ID (product_id + variant_id)
  product_id: string;
  product: Product;
  variant: ProductVariant;
  quantity: number;
  price: number; // Price at time of adding to cart
  subtotal: number; // price * quantity
  available_stock?: number;
  is_in_stock?: boolean;
  stock_issue?: string | null;
}

export interface CartValidationItem {
  product_id: string;
  variant_id?: string | null;
  product_title?: string | null;
  requested_quantity: number;
  available_stock: number;
  is_in_stock: boolean;
  made_to_order: boolean;
  status: 'ok' | 'out_of_stock' | 'insufficient_stock' | 'unavailable';
  message?: string | null;
}

export interface CartValidationResponse {
  is_valid: boolean;
  items: CartValidationItem[];
  errors: string[];
}

export interface CartSummary {
  subtotal: number;
  shipping: number;
  tax: number;
  discount: number;
  total: number;
  itemCount: number;
}

export interface Cart {
  items: CartItem[];
  summary: CartSummary;
  lastUpdated: string;
  userId?: string; // For server sync
}

export interface AddToCartParams {
  product: Product;
  variant: ProductVariant;
  quantity: number;
}

export interface UpdateCartItemParams {
  itemId: string;
  quantity: number;
}

export interface UpdateVariantParams {
  itemId: string;
  newVariant: ProductVariant;
}

export interface ApplyCouponParams {
  code: string;
}

export interface SyncCartItemPriceUpdate {
  product_id: string;
  variant_id?: string | null;
  unit_price: number;
}

export interface CartState {
  cart: Cart;
  isLoading: boolean;
  error: string | null;

  // Actions
  addItem: (params: AddToCartParams) => Promise<boolean>;
  removeItem: (itemId: string) => void;
  updateQuantity: (params: UpdateCartItemParams) => void;
  updateVariant: (params: UpdateVariantParams) => void;
  clearCart: () => void;
  applyCoupon: (params: ApplyCouponParams) => Promise<void>;
  syncItemPrices?: (updates: SyncCartItemPriceUpdate[]) => void;

  // Sync
  syncWithServer: () => Promise<void>;
  loadFromLocalStorage: () => void;

  // Calculations
  recalculatePrices: () => void;
}
