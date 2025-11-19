import type { CartItem, CartSummary } from '../types/cart';

export interface PricingConfig {
  taxRate: number; // e.g., 0.075 for 7.5% VAT
  shippingFee: number;
  freeShippingThreshold: number;
}

// Nigeria VAT is 7.5%
export const DEFAULT_PRICING_CONFIG: PricingConfig = {
  taxRate: 0.075,
  shippingFee: 2000, // ₦2,000 flat shipping
  freeShippingThreshold: 50000, // Free shipping above ₦50,000
};

/**
 * Calculate cart summary with taxes, shipping, and discounts
 * Note: For cart page, shipping and tax are 0 and calculated at checkout
 */
export function calculateCartSummary(
  items: CartItem[],
  config: PricingConfig = DEFAULT_PRICING_CONFIG,
  discountAmount: number = 0
): CartSummary {
  // Calculate subtotal
  const subtotal = items.reduce((sum, item) => sum + item.subtotal, 0);

  // Don't calculate shipping and tax for cart - they're calculated at checkout
  const shipping = 0;
  const tax = 0;

  // Apply discount
  const discount = discountAmount;

  // Calculate total (just subtotal for cart, real total calculated at checkout)
  const total = subtotal - discount;

  // Count items
  const itemCount = items.reduce((sum, item) => sum + item.quantity, 0);

  return {
    subtotal,
    shipping,
    tax,
    discount,
    total,
    itemCount,
  };
}

/**
 * Calculate item subtotal
 */
export function calculateItemSubtotal(price: number, quantity: number): number {
  return price * quantity;
}

/**
 * Get variant price (with fallback to base price)
 */
export function getVariantPrice(variantPrice?: number, basePrice?: number): number {
  return variantPrice ?? basePrice ?? 0;
}

/**
 * Format currency in Nigerian Naira
 */
export function formatCurrency(amount: number): string {
  return new Intl.NumberFormat('en-NG', {
    style: 'currency',
    currency: 'NGN',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(amount);
}

/**
 * Calculate discount percentage
 */
export function calculateDiscountPercentage(originalPrice: number, discountedPrice: number): number {
  if (originalPrice <= 0) return 0;
  return Math.round(((originalPrice - discountedPrice) / originalPrice) * 100);
}

/**
 * Apply coupon/discount code
 */
export interface CouponResult {
  isValid: boolean;
  discountAmount: number;
  discountType: 'percentage' | 'fixed';
  message: string;
}

export function applyCoupon(
  code: string,
  subtotal: number
): CouponResult {
  // This would normally call the backend API
  // For now, we'll implement some demo coupons
  const coupons: Record<string, { type: 'percentage' | 'fixed'; value: number }> = {
    'WELCOME10': { type: 'percentage', value: 10 },
    'SAVE5000': { type: 'fixed', value: 5000 },
    'FREESHIP': { type: 'fixed', value: 0 }, // Handled separately
  };

  const coupon = coupons[code.toUpperCase()];

  if (!coupon) {
    return {
      isValid: false,
      discountAmount: 0,
      discountType: 'fixed',
      message: 'Invalid coupon code',
    };
  }

  let discountAmount = 0;

  if (coupon.type === 'percentage') {
    discountAmount = subtotal * (coupon.value / 100);
  } else {
    discountAmount = coupon.value;
  }

  return {
    isValid: true,
    discountAmount: Math.round(discountAmount * 100) / 100,
    discountType: coupon.type,
    message: `Coupon applied: ${coupon.type === 'percentage' ? `${coupon.value}% off` : formatCurrency(coupon.value)}`,
  };
}
