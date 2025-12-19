import { create } from 'zustand';
import type { Currency } from '../utils/pricing';

type InterestValue = 'womenswear' | 'menswear' | null;

const CURRENCY_KEY = 'shopsoma_pref_currency';
const INTEREST_KEY = 'shopsoma_pref_interest';
const DESIGNERS_KEY = 'shopsoma_pref_designers';
const CATEGORIES_KEY = 'shopsoma_pref_categories';

const isBrowser = typeof window !== 'undefined';

const readStoredCurrency = (): Currency => {
  if (!isBrowser) return 'NGN';
  const value = window.localStorage.getItem(CURRENCY_KEY);
  return value === 'USD' ? 'USD' : 'NGN';
};

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
  currency: readStoredCurrency(),
  interest: readStoredInterest(),
  designers: readStoredList(DESIGNERS_KEY),
  categories: readStoredList(CATEGORIES_KEY),
  setCurrency: (currency) => {
    if (isBrowser) {
      window.localStorage.setItem(CURRENCY_KEY, currency);
    }
    set({ currency });
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
      interest: null,
      designers: [],
      categories: [],
    });
  },
}));
