import { useCurrencyStore } from './currencyStore';
import { create } from 'zustand';
import type { Currency } from '../utils/pricing';

type InterestValue = 'womenswear' | 'menswear' | null;

const CURRENCY_KEY = 'shopsoma_pref_currency';
const INTEREST_KEY = 'shopsoma_pref_interest';
const DESIGNERS_KEY = 'shopsoma_pref_designers';
const CATEGORIES_KEY = 'shopsoma_pref_categories';

const isBrowser = typeof window !== 'undefined';

const readStoredCurrency = (): Currency =>
  isBrowser && window.localStorage.getItem(CURRENCY_KEY) === 'USD' ? 'USD' : 'NGN';

const readStoredInterest = (): InterestValue => {
  if (!isBrowser) return null;
  const value = window.localStorage.getItem(INTEREST_KEY);
  if (value === 'menswear') return 'menswear';
  if (value === 'womenswear') return 'womenswear';
  return null;
};

const readStoredList = (key: string): string[] => {
  if (!isBrowser) return [];
  const raw = window.localStorage.getItem(key);
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) {
      return parsed.filter((item) => typeof item === 'string');
    }
    return [];
  } catch {
    return [];
  }
};

const writeStoredList = (key: string, values: string[]) => {
  if (!isBrowser) return;
  window.localStorage.setItem(key, JSON.stringify(values));
};

interface PreferenceState {
  currency: Currency;
  pendingCurrency: Currency | null;
  interest: InterestValue;
  designers: string[];
  categories: string[];
  setCurrency: (currency: Currency) => void;
  setInterest: (interest: InterestValue) => void;
  setDesigners: (designers: string[]) => void;
  setCategories: (categories: string[]) => void;
  resetPreferences: () => void;
}

export const usePreferenceStore = create<PreferenceState>((set) => ({
  currency: 'NGN',
  pendingCurrency: readStoredCurrency(),
  interest: readStoredInterest(),
  designers: readStoredList(DESIGNERS_KEY),
  categories: readStoredList(CATEGORIES_KEY),
  setCurrency: (currency) => {
    const { commerceFeatures, commerceFeaturesLoaded } = useCurrencyStore.getState();
    const pendingCurrency = commerceFeaturesLoaded ? null : currency;
    currency = commerceFeatures.usd_switching_enabled ? currency : 'NGN';
    if (isBrowser) {
      window.localStorage.setItem(CURRENCY_KEY, pendingCurrency ?? currency);
    }
    set({ currency, pendingCurrency });
  },
  setInterest: (interest) => {
    if (isBrowser) {
      if (interest === null) {
        window.localStorage.removeItem(INTEREST_KEY);
      } else {
        window.localStorage.setItem(INTEREST_KEY, interest);
      }
    }
    set({ interest });
  },
  setDesigners: (designers) => {
    writeStoredList(DESIGNERS_KEY, designers);
    set({ designers });
  },
  setCategories: (categories) => {
    writeStoredList(CATEGORIES_KEY, categories);
    set({ categories });
  },
  resetPreferences: () => {
    if (isBrowser) {
      window.localStorage.removeItem(CURRENCY_KEY);
      window.localStorage.removeItem(INTEREST_KEY);
      window.localStorage.removeItem(DESIGNERS_KEY);
      window.localStorage.removeItem(CATEGORIES_KEY);
    }
    set({
      currency: 'NGN',
      pendingCurrency: null,
      interest: null,
      designers: [],
      categories: [],
    });
  },
}));
