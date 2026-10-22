import { create } from 'zustand';
import { STORAGE_KEYS } from '../config/constants';

export type CookieCategory = 'essential' | 'preferences' | 'analytics' | 'marketing';
export type OptionalCookieCategory = Exclude<CookieCategory, 'essential'>;
export type CookieConsentStatus = 'accepted_all' | 'declined_optional' | 'custom';

export interface CookieCategoryChoices {
  essential: true;
  preferences: boolean;
  analytics: boolean;
  marketing: boolean;
}

export interface StoredCookieConsent {
  version: string;
  status: CookieConsentStatus;
  categories: CookieCategoryChoices;
  updatedAt: string;
  expiresAt: string;
}

export const COOKIE_CONSENT_STORAGE_KEY = STORAGE_KEYS.COOKIE_CONSENT;
export const COOKIE_CONSENT_COOKIE_NAME = 'shopsoma_cookie_consent';
export const COOKIE_CONSENT_CONFIG_VERSION = '1.0';
export const COOKIE_CONSENT_TTL_MS = 180 * 24 * 60 * 60 * 1000; // 180 days

export const OPTIONAL_PREFERENCE_STORAGE_KEYS = [
  'shopsoma_pref_interest',
  'shopsoma_pref_designers',
  'shopsoma_pref_categories',
  'shopsoma_pref_interest_banner',
] as const;

export const OPTIONAL_ANALYTICS_COOKIE_NAMES = ['_ga', '_gid', '_gat'] as const;
export const OPTIONAL_MARKETING_COOKIE_NAMES = ['_fbp', '_fbc', '_gcl_au'] as const;

export const DEFAULT_COOKIE_CATEGORIES: CookieCategoryChoices = {
  essential: true,
  preferences: false,
  analytics: false,
  marketing: false,
};

const ALLOWED_RECORD_KEYS = new Set(['version', 'status', 'categories', 'updatedAt', 'expiresAt']);
const ALLOWED_CATEGORY_KEYS = new Set(['essential', 'preferences', 'analytics', 'marketing']);

const isBrowser = typeof window !== 'undefined';

type CategorySubscriber = {
  category: OptionalCookieCategory;
  callback: () => void;
  hasRun: boolean;
};

const categorySubscribers = new Set<CategorySubscriber>();

function isValidStatus(value: unknown): value is CookieConsentStatus {
  return value === 'accepted_all' || value === 'declined_optional' || value === 'custom';
}

export function isConsentRecordValid(
  record: unknown,
  now = Date.now(),
  expectedVersion = COOKIE_CONSENT_CONFIG_VERSION,
): record is StoredCookieConsent {
  if (!record || typeof record !== 'object' || Array.isArray(record)) {
    return false;
  }

  const candidate = record as Record<string, unknown>;
  const recordKeys = Object.keys(candidate);
  if (recordKeys.some((key) => !ALLOWED_RECORD_KEYS.has(key))) {
    return false;
  }

  if (candidate.version !== expectedVersion || !isValidStatus(candidate.status)) {
    return false;
  }

  if (typeof candidate.updatedAt !== 'string' || typeof candidate.expiresAt !== 'string') {
    return false;
  }

  const updatedAtMs = Date.parse(candidate.updatedAt);
  const expiresAtMs = Date.parse(candidate.expiresAt);
  if (Number.isNaN(updatedAtMs) || Number.isNaN(expiresAtMs) || expiresAtMs <= now) {
    return false;
  }

  if (!candidate.categories || typeof candidate.categories !== 'object' || Array.isArray(candidate.categories)) {
    return false;
  }

  const categories = candidate.categories as Record<string, unknown>;
  const categoryKeys = Object.keys(categories);
  if (categoryKeys.some((key) => !ALLOWED_CATEGORY_KEYS.has(key))) {
    return false;
  }

  return (
    categories.essential === true &&
    typeof categories.preferences === 'boolean' &&
    typeof categories.analytics === 'boolean' &&
    typeof categories.marketing === 'boolean'
  );
}

function expireBrowserCookie(name: string): void {
  if (typeof document === 'undefined') return;
  document.cookie = `${name}=; Path=/; Max-Age=0; SameSite=Lax`;
}

function readBrowserCookie(name: string): string | null {
  if (typeof document === 'undefined' || !document.cookie) return null;
  const prefix = `${name}=`;
  const parts = document.cookie.split(';');
  for (const part of parts) {
    const trimmed = part.trim();
    if (trimmed.startsWith(prefix)) {
      return decodeURIComponent(trimmed.slice(prefix.length));
    }
  }
  return null;
}

function writeBrowserConsentCookie(consent: StoredCookieConsent): void {
  if (typeof document === 'undefined') return;
  const maxAgeSeconds = Math.max(0, Math.floor((Date.parse(consent.expiresAt) - Date.now()) / 1000));
  const secureFlag = isBrowser && window.location?.protocol === 'https:' ? '; Secure' : '';
  const encoded = encodeURIComponent(JSON.stringify(consent));
  document.cookie = `${COOKIE_CONSENT_COOKIE_NAME}=${encoded}; Path=/; Max-Age=${maxAgeSeconds}; SameSite=Lax${secureFlag}`;
}

export function clearStoredCookieConsent(): void {
  if (isBrowser) {
    try {
      window.localStorage.removeItem(COOKIE_CONSENT_STORAGE_KEY);
    } catch {
      // Ignore storage access errors in restricted environments
    }
  }
  expireBrowserCookie(COOKIE_CONSENT_COOKIE_NAME);
}

export function clearNonEssentialArtifacts(categories: CookieCategoryChoices): void {
  if (isBrowser && !categories.preferences) {
    for (const key of OPTIONAL_PREFERENCE_STORAGE_KEYS) {
      try {
        window.localStorage.removeItem(key);
      } catch {
        // Ignore storage errors
      }
    }
  }

  if (typeof document !== 'undefined') {
    if (!categories.analytics) {
      for (const name of OPTIONAL_ANALYTICS_COOKIE_NAMES) {
        expireBrowserCookie(name);
      }
      if (document.cookie) {
        for (const entry of document.cookie.split(';')) {
          const cookieName = entry.split('=')[0]?.trim();
          if (cookieName && cookieName.startsWith('_ga_')) {
            expireBrowserCookie(cookieName);
          }
        }
      }
    }

    if (!categories.marketing) {
      for (const name of OPTIONAL_MARKETING_COOKIE_NAMES) {
        expireBrowserCookie(name);
      }
    }
  }
}

export function readStoredCookieConsent(
  now = Date.now(),
  expectedVersion = COOKIE_CONSENT_CONFIG_VERSION,
): StoredCookieConsent | null {
  if (!isBrowser) return null;

  let raw: string | null = null;
  try {
    raw = window.localStorage.getItem(COOKIE_CONSENT_STORAGE_KEY);
  } catch {
    raw = null;
  }

  if (!raw) {
    raw = readBrowserCookie(COOKIE_CONSENT_COOKIE_NAME);
  }

  if (!raw) return null;

  try {
    const parsed: unknown = JSON.parse(raw);
    if (!isConsentRecordValid(parsed, now, expectedVersion)) {
      clearStoredCookieConsent();
      return null;
    }
    return {
      version: parsed.version,
      status: parsed.status,
      categories: {
        essential: true,
        preferences: parsed.categories.preferences,
        analytics: parsed.categories.analytics,
        marketing: parsed.categories.marketing,
      },
      updatedAt: parsed.updatedAt,
      expiresAt: parsed.expiresAt,
    };
  } catch {
    clearStoredCookieConsent();
    return null;
  }
}

export function createConsentRecord(
  partial: Partial<Omit<CookieCategoryChoices, 'essential'>>,
  now = Date.now(),
  version = COOKIE_CONSENT_CONFIG_VERSION,
): StoredCookieConsent {
  const categories: CookieCategoryChoices = {
    essential: true,
    preferences: Boolean(partial.preferences),
    analytics: Boolean(partial.analytics),
    marketing: Boolean(partial.marketing),
  };

  const allAccepted = categories.preferences && categories.analytics && categories.marketing;
  const allDeclined = !categories.preferences && !categories.analytics && !categories.marketing;
  const status: CookieConsentStatus = allAccepted
    ? 'accepted_all'
    : allDeclined
      ? 'declined_optional'
      : 'custom';

  return {
    version,
    status,
    categories,
    updatedAt: new Date(now).toISOString(),
    expiresAt: new Date(now + COOKIE_CONSENT_TTL_MS).toISOString(),
  };
}

export function writeStoredCookieConsent(consent: StoredCookieConsent): void {
  const sanitized: StoredCookieConsent = {
    version: consent.version,
    status: consent.status,
    categories: {
      essential: true,
      preferences: Boolean(consent.categories.preferences),
      analytics: Boolean(consent.categories.analytics),
      marketing: Boolean(consent.categories.marketing),
    },
    updatedAt: consent.updatedAt,
    expiresAt: consent.expiresAt,
  };

  if (isBrowser) {
    try {
      window.localStorage.setItem(COOKIE_CONSENT_STORAGE_KEY, JSON.stringify(sanitized));
    } catch {
      // Fall back to cookie persistence if localStorage is blocked
    }
  }
  writeBrowserConsentCookie(sanitized);
}

function notifyCategorySubscribers(categories: CookieCategoryChoices): void {
  for (const subscriber of categorySubscribers) {
    if (categories[subscriber.category] && !subscriber.hasRun) {
      subscriber.hasRun = true;
      subscriber.callback();
    } else if (!categories[subscriber.category]) {
      subscriber.hasRun = false;
    }
  }
}

function dispatchConsentEvent(consent: StoredCookieConsent | null): void {
  if (!isBrowser || typeof window.dispatchEvent !== 'function') return;
  window.dispatchEvent(
    new CustomEvent('shopsoma:cookie-consent-changed', {
      detail: consent,
    }),
  );
}

export interface CookieConsentState {
  consent: StoredCookieConsent | null;
  hasValidConsent: boolean;
  isBannerVisible: boolean;
  isPreferencesOpen: boolean;
  draftCategories: CookieCategoryChoices;
  acceptAll: () => StoredCookieConsent;
  declineOptional: () => StoredCookieConsent;
  savePreferences: (categories: Partial<Omit<CookieCategoryChoices, 'essential'>>) => StoredCookieConsent;
  openPreferences: () => void;
  closePreferences: () => void;
  setDraftCategory: (category: OptionalCookieCategory, enabled: boolean) => void;
  resetConsent: () => void;
  syncFromStorage: (now?: number, expectedVersion?: string) => void;
}

const initialConsent = readStoredCookieConsent();

export const useCookieConsentStore = create<CookieConsentState>((set, get) => ({
  consent: initialConsent,
  hasValidConsent: initialConsent !== null,
  isBannerVisible: initialConsent === null,
  isPreferencesOpen: false,
  draftCategories: initialConsent ? { ...initialConsent.categories } : { ...DEFAULT_COOKIE_CATEGORIES },

  acceptAll: () => {
    const record = createConsentRecord({
      preferences: true,
      analytics: true,
      marketing: true,
    });
    writeStoredCookieConsent(record);
    set({
      consent: record,
      hasValidConsent: true,
      isBannerVisible: false,
      isPreferencesOpen: false,
      draftCategories: { ...record.categories },
    });
    notifyCategorySubscribers(record.categories);
    dispatchConsentEvent(record);
    return record;
  },

  declineOptional: () => {
    const record = createConsentRecord({
      preferences: false,
      analytics: false,
      marketing: false,
    });
    clearNonEssentialArtifacts(record.categories);
    writeStoredCookieConsent(record);
    set({
      consent: record,
      hasValidConsent: true,
      isBannerVisible: false,
      isPreferencesOpen: false,
      draftCategories: { ...record.categories },
    });
    notifyCategorySubscribers(record.categories);
    dispatchConsentEvent(record);
    return record;
  },

  savePreferences: (partial) => {
    const record = createConsentRecord(partial);
    clearNonEssentialArtifacts(record.categories);
    writeStoredCookieConsent(record);
    set({
      consent: record,
      hasValidConsent: true,
      isBannerVisible: false,
      isPreferencesOpen: false,
      draftCategories: { ...record.categories },
    });
    notifyCategorySubscribers(record.categories);
    dispatchConsentEvent(record);
    return record;
  },

  openPreferences: () => {
    const current = get().consent;
    set({
      draftCategories: current ? { ...current.categories } : { ...DEFAULT_COOKIE_CATEGORIES },
      isBannerVisible: true,
      isPreferencesOpen: true,
    });
  },

  closePreferences: () => {
    const { hasValidConsent } = get();
    set({
      isPreferencesOpen: false,
      isBannerVisible: !hasValidConsent,
    });
  },

  setDraftCategory: (category, enabled) => {
    set((state) => ({
      draftCategories: {
        ...state.draftCategories,
        [category]: enabled,
      },
    }));
  },

  resetConsent: () => {
    clearStoredCookieConsent();
    clearNonEssentialArtifacts(DEFAULT_COOKIE_CATEGORIES);
    set({
      consent: null,
      hasValidConsent: false,
      isBannerVisible: true,
      isPreferencesOpen: false,
      draftCategories: { ...DEFAULT_COOKIE_CATEGORIES },
    });
    notifyCategorySubscribers(DEFAULT_COOKIE_CATEGORIES);
    dispatchConsentEvent(null);
  },

  syncFromStorage: (now = Date.now(), expectedVersion = COOKIE_CONSENT_CONFIG_VERSION) => {
    const stored = readStoredCookieConsent(now, expectedVersion);
    if (!stored) {
      clearNonEssentialArtifacts(DEFAULT_COOKIE_CATEGORIES);
      set({
        consent: null,
        hasValidConsent: false,
        isBannerVisible: true,
        isPreferencesOpen: false,
        draftCategories: { ...DEFAULT_COOKIE_CATEGORIES },
      });
      notifyCategorySubscribers(DEFAULT_COOKIE_CATEGORIES);
      return;
    }

    set({
      consent: stored,
      hasValidConsent: true,
      isBannerVisible: false,
      isPreferencesOpen: false,
      draftCategories: { ...stored.categories },
    });
    notifyCategorySubscribers(stored.categories);
  },
}));

export function canUseCookieCategory(
  category: CookieCategory,
  now = Date.now(),
  expectedVersion = COOKIE_CONSENT_CONFIG_VERSION,
): boolean {
  if (category === 'essential') {
    return true;
  }

  const stored = readStoredCookieConsent(now, expectedVersion);
  if (!stored) {
    return false;
  }

  return Boolean(stored.categories[category]);
}

export function runWhenCookieCategoryAllowed(
  category: OptionalCookieCategory,
  callback: () => void,
): () => void {
  const subscriber: CategorySubscriber = {
    category,
    callback,
    hasRun: false,
  };

  categorySubscribers.add(subscriber);

  if (canUseCookieCategory(category)) {
    subscriber.hasRun = true;
    callback();
  }

  return () => {
    categorySubscribers.delete(subscriber);
  };
}
