import type { AxiosRequestConfig } from 'axios';
import type { Cart, CartItem, CartSummary } from '../types/cart';
import type { Product, ProductVariant } from '../types';
import { calculateCartSummary } from '../utils/pricing';
import { STORAGE_KEYS } from '../config/constants';
import api from './api';

const CART_STORAGE_KEY = 'shopsoma_cart';
const CART_SESSION_KEY = 'shopsoma_cart_session';
const isBrowser = typeof window !== 'undefined';

function generateSessionId(): string {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random()}`;
}

function getOrCreateSessionId(): string | null {
  if (!isBrowser) return null;
  let sessionId = localStorage.getItem(CART_SESSION_KEY);
  if (!sessionId) {
    sessionId = generateSessionId();
    localStorage.setItem(CART_SESSION_KEY, sessionId);
  }
  return sessionId;
}

/**
 * Cart Service - Handles LocalStorage persistence
 */
export class CartService {
  private static async request<T = any>(config: AxiosRequestConfig): Promise<T> {
    const sessionId = getOrCreateSessionId();
    const headers = { ...(config.headers || {}) };
    // Always send session ID if it exists - needed for guest cart merge after login
    if (sessionId) {
      headers['X-Session-ID'] = sessionId;
      console.log('[CartAPI] Sending X-Session-ID header:', sessionId);
    } else {
      console.warn('[CartAPI] No session ID to send!');
    }

    try {
      const response = await api.request<T>({ ...config, headers });
      return response.data;
    } catch (error) {
      console.error('[CartAPI] Request failed:', config.method, config.url, error);
      throw error;
    }
  }

  /**
   * Get cart from LocalStorage
   */
  static getCart(): Cart {
    if (!isBrowser) {
      return this.createEmptyCart();
    }
    try {
      const cartData = localStorage.getItem(CART_STORAGE_KEY);
      if (!cartData) {
        return this.createEmptyCart();
      }

      const cart: Cart = JSON.parse(cartData);

      // Recalculate summary in case prices changed
      cart.summary = calculateCartSummary(cart.items);

      return cart;
    } catch (error) {
      console.error('Error loading cart from localStorage:', error);
      return this.createEmptyCart();
    }
  }

  /**
   * Save cart to LocalStorage
   */
  static saveCart(cart: Cart): void {
    if (!isBrowser) return;
    try {
      cart.lastUpdated = new Date().toISOString();
      localStorage.setItem(CART_STORAGE_KEY, JSON.stringify(cart));
    } catch (error) {
      console.error('Error saving cart to localStorage:', error);
    }
  }

  /**
   * Clear cart from LocalStorage
   */
  static clearCart(): void {
    if (!isBrowser) return;
    try {
      localStorage.removeItem(CART_STORAGE_KEY);
    } catch (error) {
      console.error('Error clearing cart from localStorage:', error);
    }
  }

  /**
   * Create an empty cart
   */
  static createEmptyCart(): Cart {
    return {
      items: [],
      summary: {
        subtotal: 0,
        shipping: 0,
        tax: 0,
        discount: 0,
        total: 0,
        itemCount: 0,
      },
      lastUpdated: new Date().toISOString(),
    };
  }

  /**
   * Generate cart item ID from product and variant
   */
  static generateCartItemId(productId: string, variantId: string): string {
    return `${productId}_${variantId}`;
  }

  /**
   * Find cart item by ID
   */
  static findCartItem(items: CartItem[], itemId: string): CartItem | undefined {
    return items.find(item => item.id === itemId);
  }

  /**
   * Check if item exists in cart
   */
  static itemExists(items: CartItem[], productId: string, variantId: string): boolean {
    const itemId = this.generateCartItemId(productId, variantId);
    return items.some(item => item.id === itemId);
  }

  /**
   * Sync cart with server
   */
  static async syncWithServer(cart: Cart, _userId?: string): Promise<Cart> {
    if (!this.isAuthenticated()) {
      return cart;
    }

    // Use backend merge endpoint instead of client-side merge
    try {
      const mergedCart = await this.mergeGuestCartOnServer();
      console.info('[CartAPI] syncWithServer: Merged cart successfully');
      // Clear local cart session after successful merge
      localStorage.removeItem(CART_SESSION_KEY);
      return mergedCart;
    } catch (error) {
      console.error('[CartAPI] syncWithServer: Failed to merge, falling back to fetch', error);
      // Fallback: just fetch the server cart
      return await this.fetchServerCart();
    }
  }

  static isAuthenticated(): boolean {
    if (!isBrowser) return false;
    return Boolean(localStorage.getItem(STORAGE_KEYS.ACCESS_TOKEN));
  }

  /**
   * Merge local cart with server cart (for when user logs in)
   */
  static mergeCart(localCart: Cart, serverCart: Cart): Cart {
    const mergedItems: CartItem[] = [...serverCart.items];

    // Add local items that don't exist in server cart
    localCart.items.forEach(localItem => {
      const existsInServer = mergedItems.some(item => item.id === localItem.id);
      if (!existsInServer) {
        mergedItems.push(localItem);
      } else {
        // If item exists, use the higher quantity
        const serverItem = mergedItems.find(item => item.id === localItem.id);
        if (serverItem && localItem.quantity > serverItem.quantity) {
          serverItem.quantity = localItem.quantity;
          serverItem.subtotal = serverItem.price * serverItem.quantity;
        }
      }
    });

    return {
      items: mergedItems,
      summary: calculateCartSummary(mergedItems),
      lastUpdated: new Date().toISOString(),
      userId: serverCart.userId,
    };
  }

  /**
   * Validate cart items (check stock, prices, etc.)
   */
  static async validateCart(cart: Cart): Promise<{
    isValid: boolean;
    errors: string[];
    updatedCart?: Cart;
  }> {
    // This would call the backend to validate
    // For now, just basic validation
    const errors: string[] = [];

    cart.items.forEach(item => {
      if (item.quantity <= 0) {
        errors.push(`Invalid quantity for ${item.product.title}`);
      }

      if (!item.product.made_to_order && (!item.variant.stock || item.variant.stock < item.quantity)) {
        errors.push(`${item.product.title} (${item.variant.size}) is out of stock`);
      }
    });

    return {
      isValid: errors.length === 0,
      errors,
      updatedCart: errors.length > 0 ? undefined : cart,
    };
  }

  private static transformProduct(productData: any): Product {
    if (!productData) {
      const timestamp = new Date().toISOString();
      return {
        id: '',
        vendor_id: '',
        vendor_name: 'Unknown Vendor',
        title: 'Unknown Product',
        description: '',
        base_price: 0,
        compare_at_price: 0,
        currency: 'NGN',
        category_id: null,
        category_name: '',
        size_guide: null,
        inventory_quantity: 0,
        total_stock: 0,
        status: 'active',
        is_featured: false,
        product_type: 'single',
        made_to_order: false,
        moderation_status: 'approved',
        views_count: 0,
        orders_count: 0,
        created_at: timestamp,
        updated_at: timestamp,
        variants: [],
        images: [],
      };
    }

    return {
      ...productData,
      images: productData.images ?? [],
      variants: productData.variants ?? [],
      inventory_quantity:
        productData.inventory_quantity ?? productData.total_stock ?? 0,
      total_stock: productData.total_stock ?? productData.inventory_quantity ?? 0,
    };
  }

  private static transformVariant(variantData: any, fallbackProductId = ''): ProductVariant {
    if (!variantData) {
      return {
        id: '',
        product_id: fallbackProductId,
        size: undefined,
        color: undefined,
        color_hex: undefined,
        price: 0,
        stock: 0,
        is_available: true,
      };
    }

    return {
      ...variantData,
      product_id: variantData.product_id ?? fallbackProductId,
      price: Number(variantData.price ?? 0),
      compare_at_price: variantData.compare_at_price,
      stock: variantData.stock ?? 0,
      is_available: variantData.is_available ?? true,
    };
  }

  private static transformCartSummary(summary: any): CartSummary {
    return {
      subtotal: summary?.subtotal ?? 0,
      shipping: summary?.shipping ?? 0,
      tax: summary?.tax ?? 0,
      discount: summary?.discount ?? 0,
      total: summary?.total ?? 0,
      itemCount: summary?.item_count ?? 0,
    };
  }

  private static transformCartItem(serverItem: any): CartItem {
    const product = this.transformProduct(serverItem.product);
    let variant = serverItem.variant
      ? this.transformVariant(serverItem.variant, product.id)
      : product.variants?.find((v) => v.id === serverItem.variant_id);

    if (!variant) {
      variant = this.transformVariant(null, product.id);
    }

    return {
      id: serverItem.id,
      product_id: serverItem.product_id,
      product,
      variant,
      quantity: serverItem.quantity,
      price: serverItem.price,
      subtotal: serverItem.price * serverItem.quantity,
    };
  }

  private static transformCartResponse(data: any): Cart {
    if (!data) {
      return this.createEmptyCart();
    }

    const items: CartItem[] = (data.items ?? []).map((item: any) =>
      this.transformCartItem(item)
    );

    return {
      items,
      summary: this.transformCartSummary(data.summary),
      lastUpdated: data.last_updated ?? new Date().toISOString(),
    };
  }

  static async fetchServerCart(): Promise<Cart> {
    try {
      const data = await this.request<any>({ method: 'get', url: '/cart' });
      const cart = this.transformCartResponse(data);
      console.info('[CartAPI] Fetched server cart:', cart.items.length, 'items');
      return cart;
    } catch (error) {
      console.error('[CartAPI] Failed to fetch server cart:', error);
      throw error;
    }
  }

  static async addItemToServer(productId: string, variantId: string, quantity: number): Promise<void> {
    // Always send to server for both authenticated users AND guests (using session_id)
    // Guests need server cart for merge after login
    try {
      await this.request({
        method: 'post',
        url: '/cart/items',
        data: {
          product_id: productId,
          variant_id: variantId,
          quantity,
        },
      });
      console.info('[CartAPI] Added to server cart:', productId, variantId, 'qty', quantity);
    } catch (error) {
      console.error('[CartAPI] Failed to add item to server cart:', error);
      throw error;
    }
  }

  static async updateItemOnServer(itemId: string, quantity: number): Promise<void> {
    // Always update server cart for both authenticated users AND guests
    try {
      await this.request({
        method: 'patch',
        url: `/cart/items/${itemId}`,
        data: { quantity },
      });
      console.info('[CartAPI] Updated server cart item:', itemId, 'qty', quantity);
    } catch (error) {
      console.error('[CartAPI] Failed to update server cart item:', error);
      throw error;
    }
  }

  static async removeItemFromServer(itemId: string): Promise<void> {
    // Always remove from server cart for both authenticated users AND guests
    try {
      await this.request({
        method: 'delete',
        url: `/cart/items/${itemId}`,
      });
      console.info('[CartAPI] Removed item from server cart:', itemId);
    } catch (error) {
      console.error('[CartAPI] Failed to remove item from server cart:', error);
      throw error;
    }
  }

  static async clearServerCart(): Promise<void> {
    // Always clear server cart for both authenticated users AND guests
    try {
      await this.request({
        method: 'delete',
        url: '/cart',
      });
      console.info('[CartAPI] Cleared server cart');
    } catch (error) {
      console.error('[CartAPI] Failed to clear server cart:', error);
      throw error;
    }
  }

  /**
   * Merge guest cart with user cart on the server
   */
  static async mergeGuestCartOnServer(): Promise<Cart> {
    try {
      const data = await this.request<any>({
        method: 'post',
        url: '/cart/merge-guest-cart',
      });
      const cart = this.transformCartResponse(data);
      console.info('[CartAPI] Merged guest cart on server:', cart.items.length, 'items');
      return cart;
    } catch (error) {
      console.error('[CartAPI] Failed to merge guest cart:', error);
      throw error;
    }
  }
}
