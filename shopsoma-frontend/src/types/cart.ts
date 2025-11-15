import type { Product, ProductVariant } from './product';

export interface CartItem {
  id: string; // Unique cart item ID (product_id + variant_id)
  product_id: string;
  product: Product;
  variant: ProductVariant;
  quantity: number;
  price: number; // Price at time of adding to cart
  subtotal: number; // price * quantity
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

export interface CartState {
  cart: Cart;
  isLoading: boolean;
  error: string | null;

  // Actions
  addItem: (params: AddToCartParams) => void;
  removeItem: (itemId: string) => void;
  updateQuantity: (params: UpdateCartItemParams) => void;
  updateVariant: (params: UpdateVariantParams) => void;
  clearCart: () => void;
  applyCoupon: (params: ApplyCouponParams) => Promise<void>;

  // Sync
  syncWithServer: () => Promise<void>;
  loadFromLocalStorage: () => void;

  // Calculations
  recalculatePrices: () => void;
}
