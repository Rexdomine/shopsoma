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
 * Currency conversion rates (DEPRECATED - use currencyStore instead)
 * @deprecated Use exchange rates from currencyStore for real-time rates
 */
export const EXCHANGE_RATES = {
  NGN_TO_USD: 1 / 1600, // 1 NGN = 0.000625 USD (approx 1 USD = 1600 NGN)
  USD_TO_NGN: 1600,     // 1 USD = 1600 NGN
};

export type Currency = 'NGN' | 'USD';

/**
 * Convert amount from NGN to USD
 */
export function convertNGNToUSD(amountInNGN: number): number {
  return Math.round((amountInNGN * EXCHANGE_RATES.NGN_TO_USD) * 100) / 100;
}

/**
 * Convert amount from USD to NGN
 */
export function convertUSDToNGN(amountInUSD: number): number {
  return Math.round(amountInUSD * EXCHANGE_RATES.USD_TO_NGN);
}

/**
 * Convert amount between currencies (legacy - uses hardcoded rates)
 * @deprecated Use convertCurrencyWithRates instead for real-time exchange rates
 */
export function convertCurrency(amount: number, fromCurrency: Currency, toCurrency: Currency): number {
  if (fromCurrency === toCurrency) return amount;

  if (fromCurrency === 'NGN' && toCurrency === 'USD') {
    return convertNGNToUSD(amount);
  } else {
    return convertUSDToNGN(amount);
  }
}

/**
 * Convert amount between currencies using provided exchange rates
 * @param amount - Amount to convert
 * @param fromCurrency - Source currency
 * @param toCurrency - Target currency
 * @param rates - Exchange rates object from currency store
 */
export function convertCurrencyWithRates(
  amount: number,
  fromCurrency: Currency,
  toCurrency: Currency,
  rates: { USD_TO_NGN: number; NGN_TO_USD: number }
): number {
  if (fromCurrency === toCurrency) return amount;

  if (fromCurrency === 'NGN' && toCurrency === 'USD') {
    return Math.round((amount * rates.NGN_TO_USD) * 100) / 100;
  } else {
    return Math.round(amount * rates.USD_TO_NGN);
  }
}

/**
 * Format amount in specified currency
 */
export function formatAmount(amount: number | string, currency: Currency): string {
  const symbol = currency === 'NGN' ? '₦' : '$';
  const num = typeof amount === 'number' ? amount : parseFloat(String(amount));
  const safeAmount = isNaN(num) ? 0 : num;
  return `${symbol}${safeAmount.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

/**
 * Format price with currency conversion
 * @param amountInNGN - Amount in NGN (legacy - for backwards compatibility)
 * @param currency - Target currency to display
 * @deprecated Use formatPriceWithConversion instead
 */
export function formatPriceWithCurrency(amountInNGN: number | string, currency: Currency): string {
  const num = typeof amountInNGN === 'number' ? amountInNGN : parseFloat(String(amountInNGN));
  const safeAmount = isNaN(num) ? 0 : num;
  const converted = currency === 'USD' ? convertNGNToUSD(safeAmount) : safeAmount;
  const locale = currency === 'USD' ? 'en-US' : 'en-NG';
  const minimumFractionDigits = currency === 'USD' ? 2 : 0;
  const maximumFractionDigits = currency === 'USD' ? 2 : 0;
  return new Intl.NumberFormat(locale, {
    style: 'currency',
    currency,
    minimumFractionDigits,
    maximumFractionDigits,
  }).format(converted);
}

/**
 * Format price with currency conversion (new version)
 * Converts from product's currency to user's preferred currency
 * @param amount - Price amount in the product's currency
 * @param productCurrency - Currency the product price is stored in
 * @param displayCurrency - Currency to display to the user
 * @param exchangeRates - Optional exchange rates from currency store (uses hardcoded if not provided)
 */
export function formatPriceWithConversion(
  amount: number | string,
  productCurrency: Currency,
  displayCurrency: Currency,
  exchangeRates?: { USD_TO_NGN: number; NGN_TO_USD: number }
 ): string {
  const num = typeof amount === 'number' ? amount : parseFloat(String(amount));
  const safeAmount = isNaN(num) ? 0 : num;
  const converted = exchangeRates
    ? convertCurrencyWithRates(safeAmount, productCurrency, displayCurrency, exchangeRates)
    : convertCurrency(safeAmount, productCurrency, displayCurrency);

  const locale = displayCurrency === 'USD' ? 'en-US' : 'en-NG';
  const minimumFractionDigits = displayCurrency === 'USD' ? 2 : 0;
  const maximumFractionDigits = displayCurrency === 'USD' ? 2 : 0;

  return new Intl.NumberFormat(locale, {
    style: 'currency',
    currency: displayCurrency,
    minimumFractionDigits,
    maximumFractionDigits,
  }).format(converted);
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

/**
 * Strips all commas and non-numeric characters (except a single decimal point).
 * Ensures numbers are never stored with commas in state, database, or code.
 */
export function cleanNumberString(
  value: string | number | undefined | null,
  maxDecimals: number = 2
): string {
  if (value === null || value === undefined) return '';
  const str = String(value);
  if (!str) return '';

  // Remove commas, currency symbols, and whitespace
  let cleaned = str.replace(/[,₦$£€\s]/g, '').trim();

  // Keep only digits and decimal points
  cleaned = cleaned.replace(/[^\d.]/g, '');

  // If there are multiple dots, preserve only the first dot
  const dotIndex = cleaned.indexOf('.');
  if (dotIndex !== -1) {
    const integerPart = cleaned.slice(0, dotIndex);
    const decimalPart = cleaned
      .slice(dotIndex + 1)
      .replace(/\./g, '')
      .slice(0, maxDecimals);
    return `${integerPart}.${decimalPart}`;
  }

  return cleaned;
}

/**
 * Formats a clean number string with commas for humanized presentation (e.g. 50000 -> 50,000).
 * Handles partial user input including trailing decimal points (e.g. "5000." -> "5,000.").
 */
export function formatWithCommas(
  value: string | number | undefined | null
): string {
  if (value === null || value === undefined) return '';
  const str = String(value);
  if (!str) return '';

  const cleaned = cleanNumberString(str);
  if (!cleaned) return '';

  const hasDot = cleaned.includes('.');
  if (hasDot) {
    const [integerPart, decimalPart] = cleaned.split('.');
    const formattedInteger = (integerPart || '0').replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    return `${integerPart === '' ? '' : formattedInteger}.${decimalPart ?? ''}`;
  }

  return cleaned.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

