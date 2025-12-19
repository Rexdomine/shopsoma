import { create } from 'zustand';
import type { CartState, AddToCartParams, UpdateCartItemParams, UpdateVariantParams, ApplyCouponParams, Cart, CartItem } from '../types/cart';
import { CartService } from '../services/cartService';
import { calculateCartSummary, calculateItemSubtotal, getVariantPrice, applyCoupon } from '../utils/pricing';

export const useCartStore = create<CartState>((set, get) => ({
  cart: CartService.createEmptyCart(),
  isLoading: false,
  error: null,

  /**
   * Add item to cart
   */
  addItem: ({ product, variant, quantity }: AddToCartParams) => {
    const { cart } = get();
    const itemId = CartService.generateCartItemId(product.id, variant.id);

    // Check if item already exists
    const existingItemIndex = cart.items.findIndex(item => item.id === itemId);

    let updatedItems: CartItem[];

    if (existingItemIndex > -1) {
      // Update quantity if item exists
      updatedItems = [...cart.items];
      updatedItems[existingItemIndex].quantity += quantity;
      updatedItems[existingItemIndex].subtotal = calculateItemSubtotal(
        updatedItems[existingItemIndex].price,
        updatedItems[existingItemIndex].quantity
      );
    } else {
      // Add new item
      const price = getVariantPrice(variant.price, product.base_price);
      const newItem: CartItem = {
        id: itemId,
        product_id: product.id,
        product,
        variant,
        quantity,
        price,
        subtotal: calculateItemSubtotal(price, quantity),
      };
      updatedItems = [...cart.items, newItem];
    }

    const updatedCart: Cart = {
      ...cart,
      items: updatedItems,
      summary: calculateCartSummary(updatedItems, cart.summary.discount),
    };

    CartService.saveCart(updatedCart);
    set({ cart: updatedCart, error: null });

    // Always sync to server for both authenticated users AND guests
    CartService.addItemToServer(product.id, variant.id, quantity).catch((error) => {
      console.error('[CartStore] addItem: failed to sync with server', error);
    });
  },

  /**
   * Remove item from cart
   */
  removeItem: (itemId: string) => {
    const { cart } = get();
    const updatedItems = cart.items.filter(item => item.id !== itemId);

    const updatedCart: Cart = {
      ...cart,
      items: updatedItems,
      summary: calculateCartSummary(updatedItems, cart.summary.discount),
    };

    CartService.saveCart(updatedCart);
    set({ cart: updatedCart, error: null });

    // Always sync to server for both authenticated users AND guests
    CartService.removeItemFromServer(itemId).catch((error) => {
      console.error('[CartStore] removeItem: failed to sync removal', error);
    });
  },

  /**
   * Update item quantity
   */
  updateQuantity: ({ itemId, quantity }: UpdateCartItemParams) => {
    const { cart } = get();

    if (quantity <= 0) {
      // Remove item if quantity is 0 or negative
      get().removeItem(itemId);
      return;
    }

    const updatedItems = cart.items.map(item => {
      if (item.id === itemId) {
        return {
          ...item,
          quantity,
          subtotal: calculateItemSubtotal(item.price, quantity),
        };
      }
      return item;
    });

    const updatedCart: Cart = {
      ...cart,
      items: updatedItems,
      summary: calculateCartSummary(updatedItems, cart.summary.discount),
    };

    CartService.saveCart(updatedCart);
    set({ cart: updatedCart, error: null });

    // Always sync to server for both authenticated users AND guests
    CartService.updateItemOnServer(itemId, quantity).catch((error) => {
      console.error('[CartStore] updateQuantity: failed to sync quantity', error);
    });
  },

  /**
   * Update item variant (preserves position in cart)
   */
  updateVariant: ({ itemId, newVariant }: UpdateVariantParams) => {
    const { cart } = get();

    const itemIndex = cart.items.findIndex(item => item.id === itemId);
    if (itemIndex === -1) return;

    const currentItem = cart.items[itemIndex];
    const previousItemId = currentItem.id;
    const previousProductId = currentItem.product_id;
    const previousQuantity = currentItem.quantity;
    const newItemId = CartService.generateCartItemId(currentItem.product_id, newVariant.id);

    // Check if the new variant already exists in cart
    const existingNewVariantIndex = cart.items.findIndex(item => item.id === newItemId);

    let updatedItems: CartItem[];

    if (existingNewVariantIndex > -1 && existingNewVariantIndex !== itemIndex) {
      // Merge with existing item that has the new variant
      updatedItems = cart.items.filter((_, index) => index !== itemIndex);
      updatedItems[existingNewVariantIndex] = {
        ...updatedItems[existingNewVariantIndex],
        quantity: updatedItems[existingNewVariantIndex].quantity + currentItem.quantity,
        subtotal: calculateItemSubtotal(
          updatedItems[existingNewVariantIndex].price,
          updatedItems[existingNewVariantIndex].quantity + currentItem.quantity
        ),
      };
    } else {
      // Update variant in place (preserves order)
      const newPrice = getVariantPrice(newVariant.price, currentItem.product.base_price);
      updatedItems = [...cart.items];
      updatedItems[itemIndex] = {
        ...currentItem,
        id: newItemId,
        variant: newVariant,
        price: newPrice,
        subtotal: calculateItemSubtotal(newPrice, currentItem.quantity),
      };
    }

    const updatedCart: Cart = {
      ...cart,
      items: updatedItems,
      summary: calculateCartSummary(updatedItems, cart.summary.discount),
    };

    CartService.saveCart(updatedCart);
    set({ cart: updatedCart, error: null });

    // Always sync to server for both authenticated users AND guests
    CartService.removeItemFromServer(previousItemId)
      .catch((error) => {
        console.error('[CartStore] updateVariant: failed to remove old variant', error);
      })
      .finally(() => {
        CartService.addItemToServer(previousProductId, newVariant.id, previousQuantity).catch((error) => {
          console.error('[CartStore] updateVariant: failed to add updated variant', error);
        });
      });
  },

  /**
   * Clear cart
   */
  clearCart: () => {
    const emptyCart = CartService.createEmptyCart();
    CartService.clearCart();
    set({ cart: emptyCart, error: null });

    // Always sync to server for both authenticated users AND guests
    CartService.clearServerCart().catch((error) => {
      console.error('[CartStore] clearCart: failed to clear server cart', error);
    });
  },

  /**
   * Apply coupon code
   */
  applyCoupon: async ({ code }: ApplyCouponParams) => {
    const { cart } = get();

    try {
      set({ isLoading: true, error: null });

      const couponResult = applyCoupon(code, cart.summary.subtotal);

      if (!couponResult.isValid) {
        set({ error: couponResult.message, isLoading: false });
        return;
      }

      const updatedCart: Cart = {
        ...cart,
        summary: calculateCartSummary(cart.items, couponResult.discountAmount),
      };

      CartService.saveCart(updatedCart);
      set({ cart: updatedCart, isLoading: false, error: null });
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : 'Failed to apply coupon',
        isLoading: false,
      });
    }
  },

  /**
   * Sync cart with server
   */
  syncWithServer: async () => {
    const { cart } = get();

    try {
      set({ isLoading: true, error: null });

      const syncedCart = await CartService.syncWithServer(cart, cart.userId);

      CartService.saveCart(syncedCart);
      set({ cart: syncedCart, isLoading: false, error: null });
    } catch (error) {
      console.error('[CartStore] syncWithServer failed:', error);
      set({
        error: error instanceof Error ? error.message : 'Failed to sync cart',
        isLoading: false,
      });
    }
  },

  /**
   * Load cart from LocalStorage
   */
  loadFromLocalStorage: () => {
    const cart = CartService.getCart();
    set({ cart, error: null });

    if (CartService.isAuthenticated()) {
      CartService.fetchServerCart()
        .then((serverCart) => {
          CartService.saveCart(serverCart);
          set({ cart: serverCart });
        })
        .catch((error) => {
          console.error('Failed to hydrate cart from server:', error);
        });
    }
  },

  /**
   * Recalculate prices (useful when prices change or tax rates update)
   */
  recalculatePrices: () => {
    const { cart } = get();

    const updatedCart: Cart = {
      ...cart,
      summary: calculateCartSummary(cart.items, cart.summary.discount),
    };

    CartService.saveCart(updatedCart);
    set({ cart: updatedCart });
  },
}));

// Initialize cart from localStorage on first load
if (typeof window !== 'undefined') {
  useCartStore.getState().loadFromLocalStorage();
}
