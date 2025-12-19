/**
 * Custom hook for currency management
 * Provides easy access to currency conversion and formatting
 */

import { useCurrencyStore } from '../store/currencyStore';
import type { Currency } from '../store/currencyStore';

export function useCurrency() {
  const {
    currentCurrency,
    setCurrency,
    toggleCurrency,
    convertPrice,
    formatPrice,
    exchangeRates,
    fetchExchangeRate,
    isLoadingRates,
  } = useCurrencyStore();

  /**
   * Convert a price from NGN (base currency) to the current currency
   * All prices in the database are stored in NGN
   */
  const convertFromBase = (ngnPrice: number): number => {
    return convertPrice(ngnPrice, 'NGN', currentCurrency);
  };

  /**
   * Format a price in NGN to the current currency with proper symbol
   */
  const formatBasePrice = (ngnPrice: number): string => {
    const converted = convertFromBase(ngnPrice);
    return formatPrice(converted, currentCurrency);
  };

  /**
   * Get the currency symbol for the current currency
   */
  const getCurrencySymbol = (): string => {
    return currentCurrency === 'NGN' ? '₦' : '$';
  };

  /**
   * Get the currency code for the current currency
   */
  const getCurrencyCode = (): Currency => {
    return currentCurrency;
  };

  return {
    currentCurrency,
    setCurrency,
    toggleCurrency,
    convertPrice,
    formatPrice,
    convertFromBase,
    formatBasePrice,
    getCurrencySymbol,
    getCurrencyCode,
    exchangeRates,
    fetchExchangeRate,
    isLoadingRates,
  };
}
