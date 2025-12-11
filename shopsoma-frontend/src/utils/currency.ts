/**
 * Currency utility functions
 * Helper functions for currency conversion and formatting
 */

import type { Currency } from '../store/currencyStore';

export const CURRENCY_SYMBOLS: Record<Currency, string> = {
  NGN: '₦',
  USD: '$',
};

export const CURRENCY_CODES: Record<Currency, string> = {
  NGN: 'NGN',
  USD: 'USD',
};

/**
 * Format price with currency symbol
 */
export function formatCurrency(
  amount: number,
  currency: Currency = 'NGN',
  options?: Intl.NumberFormatOptions
): string {
  const locale = currency === 'NGN' ? 'en-NG' : 'en-US';

  const formatted = new Intl.NumberFormat(locale, {
    style: 'currency',
    currency: currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
    ...options,
  }).format(amount);

  return formatted;
}

/**
 * Convert price from one currency to another
 */
export function convertCurrency(
  amount: number,
  fromCurrency: Currency,
  toCurrency: Currency,
  exchangeRate: number
): number {
  if (fromCurrency === toCurrency) {
    return amount;
  }

  return amount * exchangeRate;
}

/**
 * Get currency symbol
 */
export function getCurrencySymbol(currency: Currency): string {
  return CURRENCY_SYMBOLS[currency];
}

/**
 * Parse price string to number
 */
export function parsePrice(priceString: string): number {
  const cleaned = priceString.replace(/[₦$,\s]/g, '');
  return parseFloat(cleaned) || 0;
}

/**
 * Format price range (e.g., "$10.00 - $20.00")
 */
export function formatPriceRange(
  minPrice: number,
  maxPrice: number,
  currency: Currency = 'NGN'
): string {
  return `${formatCurrency(minPrice, currency)} - ${formatCurrency(maxPrice, currency)}`;
}
