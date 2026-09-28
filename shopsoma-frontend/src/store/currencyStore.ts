/**
 * Currency Store
 * Manages currency selection and conversion between NGN and USD
 */
import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { getCommerceFeatures, type CommerceFeatures, getExchangeRate } from '../services/settingsService';
import { usePreferenceStore } from './preferenceStore';

export type Currency = 'NGN' | 'USD';

interface ExchangeRates {
  NGN_TO_USD: number;
  USD_TO_NGN: number;
  lastUpdated: string;
}

interface CurrencyState {
  currentCurrency: Currency;
  commerceFeatures: CommerceFeatures;
  commerceFeaturesLoaded: boolean;
  fetchCommerceFeatures: () => Promise<void>;
  applyCommerceFeatures: (flags: CommerceFeatures) => void;
  exchangeRates: ExchangeRates;
  isLoadingRates: boolean;

  // Actions
  setCurrency: (currency: Currency) => void;
  toggleCurrency: () => void;
  updateExchangeRates: (rates: Partial<ExchangeRates>) => void;
  fetchExchangeRate: () => Promise<void>;

  // Utility functions
  convertPrice: (price: number, from: Currency, to: Currency) => number;
  formatPrice: (price: number, currency?: Currency) => string;
}

// Default exchange rates (should be updated from API)
const DEFAULT_EXCHANGE_RATES: ExchangeRates = {
  NGN_TO_USD: 0.0012, // 1 NGN = 0.0012 USD (approximately 1 USD = 833 NGN)
  USD_TO_NGN: 833,    // 1 USD = 833 NGN
  lastUpdated: new Date().toISOString(),
};

export const useCurrencyStore = create<CurrencyState>()(
  persist(
    (set, get) => ({
      currentCurrency: 'NGN',
      commerceFeatures: { stripe_enabled: false, usd_switching_enabled: false },
      commerceFeaturesLoaded: false,
      applyCommerceFeatures: (flags) => {
        const safe = {
          stripe_enabled: flags.stripe_enabled === true,
          usd_switching_enabled: flags.usd_switching_enabled === true,
        };
        const preferred = usePreferenceStore.getState().pendingCurrency ?? usePreferenceStore.getState().currency;
        set({ commerceFeatures: safe, commerceFeaturesLoaded: true });
        get().setCurrency(safe.usd_switching_enabled ? preferred : 'NGN');
      },
      fetchCommerceFeatures: async () => {
        try {
          get().applyCommerceFeatures(await getCommerceFeatures());
        } catch {
          get().applyCommerceFeatures({ stripe_enabled: false, usd_switching_enabled: false });
        }
      },
      exchangeRates: DEFAULT_EXCHANGE_RATES,
      isLoadingRates: false,

      setCurrency: (currency: Currency) => {
        set({ currentCurrency: get().commerceFeatures.usd_switching_enabled ? currency : 'NGN' });
        try {
          usePreferenceStore.getState().setCurrency(currency);
        } catch (error) {
          console.error('[CurrencyStore] Failed to persist preferred currency', {
            currency,
            error,
          });
        }
      },

      toggleCurrency: () => {
        get().setCurrency(get().currentCurrency === 'NGN' ? 'USD' : 'NGN');
      },

      updateExchangeRates: (rates: Partial<ExchangeRates>) => {
        set((state) => ({
          exchangeRates: {
            ...state.exchangeRates,
            ...rates,
            lastUpdated: new Date().toISOString(),
          },
        }));
      },

      fetchExchangeRate: async () => {
        set({ isLoadingRates: true });
        try {
          const response = await getExchangeRate();
          const usdToNgn = response.rate;
          const ngnToUsd = 1 / usdToNgn;

          set({
            exchangeRates: {
              USD_TO_NGN: usdToNgn,
              NGN_TO_USD: ngnToUsd,
              lastUpdated: response.updated_at || new Date().toISOString(),
            },
            isLoadingRates: false,
          });
        } catch (error) {
          console.error('Failed to fetch exchange rate:', error);
          // Keep using cached/default rates on error
          set({ isLoadingRates: false });
        }
      },

      convertPrice: (price: number, from: Currency, to: Currency): number => {
        if (from === to) return price;

        const { exchangeRates } = get();

        if (from === 'NGN' && to === 'USD') {
          return price * exchangeRates.NGN_TO_USD;
        }

        if (from === 'USD' && to === 'NGN') {
          return price * exchangeRates.USD_TO_NGN;
        }

        return price;
      },

      formatPrice: (price: number, currency?: Currency): string => {
        const curr = currency || get().currentCurrency;

        if (curr === 'NGN') {
          return `₦${price.toLocaleString('en-NG', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2
          })}`;
        }

        if (curr === 'USD') {
          return `$${price.toLocaleString('en-US', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2
          })}`;
        }

        return price.toString();
      },
    }),
    {
      name: 'shopsoma-currency',
      // Flags are never persisted; saved USD cannot bypass the initial closed gate.
      merge: (persisted, current) => ({ ...current, exchangeRates: (persisted as Partial<CurrencyState>)?.exchangeRates ?? current.exchangeRates, currentCurrency: 'NGN' }),
      partialize: (state) => ({
        currentCurrency: state.currentCurrency,
        exchangeRates: state.exchangeRates,
      }),
    }
  )
);
