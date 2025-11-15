import type { Cart, CartItem } from '../types/cart';
import { calculateCartSummary } from '../utils/pricing';

const CART_STORAGE_KEY = 'shopsoma_cart';

/**
 * Cart Service - Handles LocalStorage persistence
 */
export class CartService {
  /**
   * Get cart from LocalStorage
   */
  static getCart(): Cart {
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
   * Sync cart with server (placeholder for future implementation)
   */
  static async syncWithServer(cart: Cart, userId?: string): Promise<Cart> {
    // This will be implemented when we add the backend cart endpoints
    // For now, just return the local cart
    console.log('Server sync not yet implemented');
    return cart;
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

      if (!item.variant.stock || item.variant.stock < item.quantity) {
        errors.push(`${item.product.title} (${item.variant.size}) is out of stock`);
      }
    });

    return {
      isValid: errors.length === 0,
      errors,
      updatedCart: errors.length > 0 ? undefined : cart,
    };
  }
}
