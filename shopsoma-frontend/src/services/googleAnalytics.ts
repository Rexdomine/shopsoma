import {
  canUseCookieCategory,
  useCookieConsentStore,
  type CookieCategoryChoices,
} from '../store/cookieConsentStore';

declare global {
  interface Window {
    dataLayer?: unknown[];
    gtag?: (...args: any[]) => void;
    [key: `ga-disable-${string}`]: boolean | undefined;
  }
}

export const GA_SCRIPT_ID = 'shopsoma-ga4-gtag';

export const UTM_PARAM_KEYS = [
  'utm_source',
  'utm_medium',
  'utm_campaign',
  'utm_content',
  'utm_term',
  'utm_id',
  'utm_source_platform',
  'utm_creative_format',
  'utm_marketing_tactic',
] as const;

export type UtmParamKey = (typeof UTM_PARAM_KEYS)[number];

export type CampaignAttribution = Partial<Record<UtmParamKey, string>>;

export interface SanitizedPageContext {
  pageLocation: string;
  pagePath: string;
  pageTitle: string;
  pageReferrer?: string;
  locationKey: string;
  attribution: CampaignAttribution;
}

export interface TrackPageViewOptions {
  pathname?: string;
  search?: string;
  title?: string;
  referrer?: string;
  origin?: string;
  measurementId?: string;
  debugMode?: boolean;
}

const SENSITIVE_PARAM_KEYS = new Set([
  'email',
  'mail',
  'useremail',
  'customeremail',
  'guestemail',
  'vendoremail',
  'name',
  'fullname',
  'firstname',
  'lastname',
  'middlename',
  'username',
  'displayname',
  'customername',
  'phone',
  'phonenumber',
  'mobile',
  'mobilenumber',
  'tel',
  'telephone',
  'whatsapp',
  'address',
  'address1',
  'address2',
  'addressline1',
  'addressline2',
  'street',
  'streetaddress',
  'postalcode',
  'postcode',
  'zipcode',
  'zip',
  'token',
  'accesstoken',
  'refreshtoken',
  'idtoken',
  'resettoken',
  'verifytoken',
  'verificationtoken',
  'activationtoken',
  'claimtoken',
  'authtoken',
  'sessiontoken',
  'csrf',
  'jwt',
  'otp',
  'code',
  'passcode',
  'pin',
  'password',
  'passwd',
  'pwd',
  'secret',
  'clientsecret',
  'paymentintentclientsecret',
  'setupintentclientsecret',
  'apikey',
  'key',
  'signature',
  'sig',
  'capability',
  'checkoutcapability',
  'reference',
  'trxref',
  'txref',
]);

const SENSITIVE_KEY_SUFFIXES = [
  'email',
  'password',
  'passwd',
  'token',
  'secret',
  'phone',
  'telephone',
  'address',
  'postcode',
  'postalcode',
  'otp',
  'capability',
];

const INTERNAL_DEBUG_PARAM_KEYS = new Set(['ga_debug', 'debug_mode']);

const EMAIL_PATTERN = /[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i;
const EMAIL_GLOBAL_PATTERN = /[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi;
const JWT_PATTERN = /\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b/;
const JWT_GLOBAL_PATTERN = /\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b/g;
const UUID_GLOBAL_PATTERN =
  /\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/gi;
const PHONE_PATTERN =
  /(?:^|[^\w-])(?:\+\d{1,3}[\s().-]?\d{2,4}[\s().-]?\d{3,4}[\s().-]?\d{3,4}|\b0[789][01]\d[\s.-]?\d{3}[\s.-]?\d{4}\b)(?:$|[^\w-])/;

const PLACEHOLDER_MEASUREMENT_IDS = new Set([
  'G-XXXXXXXXXX',
  'G-XXXXXXXX',
  'G-0000000000',
  'G-YOUR_ID',
  'G-PLACEHOLDER',
  'YOUR_GA_MEASUREMENT_ID',
  'YOUR_GOOGLE_ANALYTICS_ID',
]);

let initializedMeasurementId: string | null = null;
let lastTrackedLocationKey: string | null = null;
let lastTrackedCleanLocation: string | null = null;
let pendingLandingAttribution: CampaignAttribution | null = null;
let activeCampaignAttribution: CampaignAttribution = {};
let pendingExternalReferrer: string | undefined;
let hasSentInitialPageView = false;
let sessionDebugMode = false;
let consentSubscriptionCleanup: (() => void) | null = null;

function safeDecodeURIComponent(value: string): string {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

function normalizeParamKey(key: string): string {
  return key.trim().toLowerCase().replace(/[-_\s.]/g, '');
}

export function isSensitiveParamKey(key: string): boolean {
  const normalized = normalizeParamKey(key);
  if (!normalized) return false;
  if (UTM_PARAM_KEYS.includes(key.trim().toLowerCase() as UtmParamKey)) {
    return false;
  }
  if (SENSITIVE_PARAM_KEYS.has(normalized)) {
    return true;
  }
  return SENSITIVE_KEY_SUFFIXES.some((suffix) => normalized.endsWith(suffix));
}

export function containsPersonalInfo(rawValue: string): boolean {
  const trimmed = rawValue.trim();
  if (!trimmed) return false;

  const decoded = safeDecodeURIComponent(trimmed);
  for (const candidate of [trimmed, decoded]) {
    if (EMAIL_PATTERN.test(candidate) || JWT_PATTERN.test(candidate)) {
      return true;
    }
    const withoutUuids = candidate.replace(UUID_GLOBAL_PATTERN, '');
    if (PHONE_PATTERN.test(withoutUuids)) {
      return true;
    }
  }

  return false;
}

export function redactPersonalInfoFromText(value: string): string {
  if (!value) return '';
  const decoded = safeDecodeURIComponent(value);
  return decoded
    .replace(EMAIL_GLOBAL_PATTERN, '[redacted-email]')
    .replace(JWT_GLOBAL_PATTERN, '[redacted-token]')
    .replace(
      /(?:^|(\s))(?:\+\d{1,3}[\s().-]?\d{2,4}[\s().-]?\d{3,4}[\s().-]?\d{3,4}|\b0[789][01]\d[\s.-]?\d{3}[\s.-]?\d{4}\b)/g,
      '$1[redacted-phone]',
    );
}

export function isValidGaMeasurementId(value?: string | null): boolean {
  if (!value) return false;
  const cleaned = value.trim().replace(/^['"]|['"]$/g, '').toUpperCase();
  if (!cleaned || PLACEHOLDER_MEASUREMENT_IDS.has(cleaned) || /^G-X+$/i.test(cleaned)) {
    return false;
  }
  return /^G-[A-Z0-9]{4,20}$/.test(cleaned);
}

export function getConfiguredGaMeasurementId(explicitMeasurementId?: string): string {
  if (explicitMeasurementId !== undefined) {
    const cleanedExplicit = explicitMeasurementId.trim().replace(/^['"]|['"]$/g, '').toUpperCase();
    return isValidGaMeasurementId(cleanedExplicit) ? cleanedExplicit : '';
  }

  const enableFlag = String(import.meta.env.VITE_ENABLE_ANALYTICS ?? '')
    .trim()
    .toLowerCase();
  const rawMeasurementId = String(
    import.meta.env.VITE_GA_MEASUREMENT_ID ??
      import.meta.env.VITE_GOOGLE_ANALYTICS_ID ??
      '',
  )
    .trim()
    .replace(/^['"]|['"]$/g, '')
    .toUpperCase();

  if (enableFlag === 'false' || enableFlag === '0') {
    return '';
  }

  return isValidGaMeasurementId(rawMeasurementId) ? rawMeasurementId : '';
}

export function isGaDebugModeEnabled(search?: string, explicitDebugMode?: boolean): boolean {
  if (typeof explicitDebugMode === 'boolean') {
    if (explicitDebugMode) {
      sessionDebugMode = true;
    }
    return explicitDebugMode;
  }

  const envDebug = String(import.meta.env.VITE_GA_DEBUG_MODE ?? '')
    .trim()
    .toLowerCase();
  if (envDebug === 'true' || envDebug === '1') {
    return true;
  }

  const rawSearch =
    search ?? (typeof window !== 'undefined' ? window.location.search : '');
  if (rawSearch) {
    const params = new URLSearchParams(rawSearch);
    const gaDebug = params.get('ga_debug')?.trim().toLowerCase();
    const debugMode = params.get('debug_mode')?.trim().toLowerCase();
    if (gaDebug === '1' || gaDebug === 'true' || debugMode === '1' || debugMode === 'true') {
      sessionDebugMode = true;
      return true;
    }
  }

  return sessionDebugMode;
}

export function extractCampaignAttribution(search: string): CampaignAttribution {
  const attribution: CampaignAttribution = {};
  if (!search) return attribution;

  const params = new URLSearchParams(search.startsWith('?') ? search : `?${search}`);
  for (const key of UTM_PARAM_KEYS) {
    const rawValue = params.get(key);
    if (!rawValue) continue;
    const trimmed = rawValue.trim();
    if (!trimmed || containsPersonalInfo(trimmed)) continue;
    attribution[key] = trimmed.slice(0, 150);
  }

  return attribution;
}

export function hasCampaignAttribution(attribution?: CampaignAttribution | null): boolean {
  if (!attribution) return false;
  return UTM_PARAM_KEYS.some((key) => Boolean(attribution[key]));
}

function sanitizePathname(pathname: string): string {
  const normalized = pathname.startsWith('/') ? pathname : `/${pathname}`;
  return normalized
    .split('/')
    .map((segment) => {
      if (!segment) return '';
      if (containsPersonalInfo(segment)) {
        return '[redacted]';
      }
      return segment;
    })
    .join('/');
}

export function sanitizeReferrerUrl(
  rawReferrer?: string | null,
  currentOrigin?: string,
): string | undefined {
  const trimmed = (rawReferrer ?? '').trim();
  if (!trimmed) return undefined;

  try {
    const parsed = new URL(trimmed);
    if (currentOrigin && parsed.origin === currentOrigin) {
      return undefined;
    }

    const sanitizedPath = sanitizePathname(parsed.pathname);
    const safeParams = new URLSearchParams();
    parsed.searchParams.forEach((value, key) => {
      if (isSensitiveParamKey(key) || INTERNAL_DEBUG_PARAM_KEYS.has(key.toLowerCase())) {
        return;
      }
      if (containsPersonalInfo(value)) {
        return;
      }
      if (UTM_PARAM_KEYS.includes(key.toLowerCase() as UtmParamKey)) {
        safeParams.set(key.toLowerCase(), value.trim());
      }
    });

    const query = safeParams.toString();
    return `${parsed.origin}${sanitizedPath}${query ? `?${query}` : ''}`;
  } catch {
    return undefined;
  }
}

export function sanitizeAnalyticsUrl(
  rawUrlOrPath: string,
  baseOrigin = typeof window !== 'undefined' && window.location?.origin
    ? window.location.origin
    : 'https://shopsoma.com',
  fallbackAttribution?: CampaignAttribution | null,
): {
  pageLocation: string;
  cleanPageLocation: string;
  pagePath: string;
  locationKey: string;
  attribution: CampaignAttribution;
} {
  let parsed: URL;
  try {
    parsed = new URL(rawUrlOrPath, baseOrigin);
  } catch {
    parsed = new URL('/', baseOrigin);
  }

  const sanitizedPathname = sanitizePathname(parsed.pathname);
  const directAttribution = extractCampaignAttribution(parsed.search);
  const effectiveAttribution: CampaignAttribution = hasCampaignAttribution(directAttribution)
    ? directAttribution
    : fallbackAttribution && hasCampaignAttribution(fallbackAttribution)
      ? { ...fallbackAttribution }
      : {};

  const safeParams = new URLSearchParams();
  const directSafeParams = new URLSearchParams();
  const nonUtmParams = new URLSearchParams();

  parsed.searchParams.forEach((rawValue, rawKey) => {
    const trimmedKey = rawKey.trim();
    const lowerKey = trimmedKey.toLowerCase();
    if (!trimmedKey) return;
    if (INTERNAL_DEBUG_PARAM_KEYS.has(lowerKey)) return;
    if (isSensitiveParamKey(trimmedKey)) return;

    const trimmedValue = rawValue.trim();
    if (!trimmedValue || containsPersonalInfo(trimmedValue)) return;

    if (UTM_PARAM_KEYS.includes(lowerKey as UtmParamKey)) {
      const normalizedUtm = trimmedValue.slice(0, 150);
      safeParams.set(lowerKey, normalizedUtm);
      directSafeParams.set(lowerKey, normalizedUtm);
    } else {
      safeParams.set(trimmedKey, trimmedValue);
      directSafeParams.set(trimmedKey, trimmedValue);
      nonUtmParams.set(trimmedKey, trimmedValue);
    }
  });

  if (!hasCampaignAttribution(directAttribution) && hasCampaignAttribution(effectiveAttribution)) {
    for (const key of UTM_PARAM_KEYS) {
      const value = effectiveAttribution[key];
      if (value) {
        safeParams.set(key, value);
      }
    }
  }

  const queryString = safeParams.toString();
  const directQueryString = directSafeParams.toString();
  const nonUtmQueryString = nonUtmParams.toString();
  const pagePath = `${sanitizedPathname}${queryString ? `?${queryString}` : ''}`;
  const directPagePath = `${sanitizedPathname}${directQueryString ? `?${directQueryString}` : ''}`;
  const cleanPagePath = `${sanitizedPathname}${nonUtmQueryString ? `?${nonUtmQueryString}` : ''}`;

  return {
    pageLocation: `${parsed.origin}${pagePath}`,
    cleanPageLocation: `${parsed.origin}${cleanPagePath}`,
    pagePath,
    locationKey: directPagePath,
    attribution: effectiveAttribution,
  };
}

export function sanitizeEventParameters(
  params?: Record<string, unknown>,
): Record<string, string | number | boolean> {
  const sanitized: Record<string, string | number | boolean> = {};
  if (!params || typeof params !== 'object') {
    return sanitized;
  }

  for (const [key, rawValue] of Object.entries(params)) {
    if (!key || isSensitiveParamKey(key)) {
      continue;
    }

    if (typeof rawValue === 'boolean' || typeof rawValue === 'number') {
      if (Number.isFinite(rawValue) || typeof rawValue === 'boolean') {
        sanitized[key] = rawValue;
      }
      continue;
    }

    if (typeof rawValue === 'string') {
      const trimmed = rawValue.trim();
      if (!trimmed) continue;
      if (key === 'page_location' || key === 'page_referrer') {
        const sanitizedUrl = sanitizeAnalyticsUrl(trimmed);
        sanitized[key] = sanitizedUrl.pageLocation;
        continue;
      }
      if (key === 'page_path') {
        const sanitizedUrl = sanitizeAnalyticsUrl(trimmed);
        sanitized[key] = sanitizedUrl.pagePath;
        continue;
      }
      if (containsPersonalInfo(trimmed)) {
        sanitized[key] = redactPersonalInfoFromText(trimmed);
      } else {
        sanitized[key] = trimmed;
      }
    }
  }

  return sanitized;
}

export function captureNavigationContext(options?: {
  pathname?: string;
  search?: string;
  referrer?: string;
  origin?: string;
}): void {
  if (typeof window === 'undefined' && !options) return;

  const search = options?.search ?? (typeof window !== 'undefined' ? window.location.search : '');
  const origin =
    options?.origin ??
    (typeof window !== 'undefined' && window.location?.origin
      ? window.location.origin
      : 'https://shopsoma.com');
  const referrer =
    options?.referrer ?? (typeof document !== 'undefined' ? document.referrer : '');

  isGaDebugModeEnabled(search);

  const incomingAttribution = extractCampaignAttribution(search);
  if (hasCampaignAttribution(incomingAttribution)) {
    pendingLandingAttribution = incomingAttribution;
    activeCampaignAttribution = { ...incomingAttribution };
  }

  if (!hasSentInitialPageView && !pendingExternalReferrer && referrer) {
    const sanitizedRef = sanitizeReferrerUrl(referrer, origin);
    if (sanitizedRef) {
      pendingExternalReferrer = sanitizedRef;
    }
  }
}

function ensureGtagFunction(): (...args: any[]) => void {
  window.dataLayer = window.dataLayer || [];
  if (typeof window.gtag !== 'function') {
    window.gtag = function gtag() {
      // Push standard Arguments object to dataLayer as expected by gtag.js
      // eslint-disable-next-line prefer-rest-params
      window.dataLayer!.push(arguments);
    };
  }
  return window.gtag;
}

function buildConsentModePayload(categories?: Partial<CookieCategoryChoices>) {
  const analyticsAllowed = categories?.analytics ?? canUseCookieCategory('analytics');
  const marketingAllowed = categories?.marketing ?? canUseCookieCategory('marketing');

  return {
    analytics_storage: analyticsAllowed ? 'granted' : 'denied',
    ad_storage: marketingAllowed ? 'granted' : 'denied',
    ad_user_data: marketingAllowed ? 'granted' : 'denied',
    ad_personalization: marketingAllowed ? 'granted' : 'denied',
  } as const;
}

function applyCampaignToGtag(
  gtag: (...args: any[]) => void,
  attribution: CampaignAttribution,
): void {
  if (!hasCampaignAttribution(attribution)) return;

  const campaignConfig: Record<string, string> = {};
  if (attribution.utm_source) campaignConfig.source = attribution.utm_source;
  if (attribution.utm_medium) campaignConfig.medium = attribution.utm_medium;
  if (attribution.utm_campaign) campaignConfig.name = attribution.utm_campaign;
  if (attribution.utm_content) campaignConfig.content = attribution.utm_content;
  if (attribution.utm_term) campaignConfig.term = attribution.utm_term;
  if (attribution.utm_id) campaignConfig.id = attribution.utm_id;

  if (Object.keys(campaignConfig).length > 0) {
    gtag('set', 'campaign', campaignConfig);
  }
}

export function initializeGoogleAnalytics(options?: {
  measurementId?: string;
  debugMode?: boolean;
}): boolean {
  if (typeof window === 'undefined' || typeof document === 'undefined') {
    return false;
  }

  const measurementId = getConfiguredGaMeasurementId(options?.measurementId);
  if (!measurementId) {
    return false;
  }

  if (!canUseCookieCategory('analytics')) {
    window[`ga-disable-${measurementId}`] = true;
    return false;
  }

  window[`ga-disable-${measurementId}`] = false;
  const gtag = ensureGtagFunction();
  const consentPayload = buildConsentModePayload();
  const marketingAllowed = consentPayload.ad_storage === 'granted';
  const debugMode = isGaDebugModeEnabled(undefined, options?.debugMode);

  let scriptEl = document.getElementById(GA_SCRIPT_ID) as HTMLScriptElement | null;
  const expectedSrc = `https://www.googletagmanager.com/gtag/js?id=${encodeURIComponent(measurementId)}`;
  if (!scriptEl) {
    scriptEl = document.createElement('script');
    scriptEl.id = GA_SCRIPT_ID;
    scriptEl.async = true;
    scriptEl.src = expectedSrc;
    document.head.appendChild(scriptEl);
  } else if (scriptEl.src !== expectedSrc) {
    scriptEl.src = expectedSrc;
  }

  if (initializedMeasurementId !== measurementId) {
    gtag('consent', 'default', consentPayload);
    gtag('js', new Date());
    gtag('config', measurementId, {
      send_page_view: false,
      allow_google_signals: marketingAllowed,
      allow_ad_personalization_signals: marketingAllowed,
      ...(debugMode ? { debug_mode: true } : {}),
    });
    initializedMeasurementId = measurementId;
  } else {
    gtag('consent', 'update', consentPayload);
  }

  return true;
}

export function deactivateGoogleAnalytics(explicitMeasurementId?: string): void {
  if (typeof window === 'undefined') return;

  const measurementId =
    getConfiguredGaMeasurementId(explicitMeasurementId) || initializedMeasurementId || '';
  if (measurementId) {
    window[`ga-disable-${measurementId}`] = true;
  }

  if (typeof window.gtag === 'function') {
    window.gtag('consent', 'update', {
      analytics_storage: 'denied',
      ad_storage: 'denied',
      ad_user_data: 'denied',
      ad_personalization: 'denied',
    });
  }

  // Allow re-tracking the current page if the visitor later re-grants analytics consent
  lastTrackedLocationKey = null;
}

export function trackPageView(options?: TrackPageViewOptions): boolean {
  if (typeof window === 'undefined') return false;

  const pathname = options?.pathname ?? window.location.pathname ?? '/';
  const search = options?.search ?? window.location.search ?? '';
  const origin =
    options?.origin ??
    (window.location?.origin && window.location.origin !== 'null'
      ? window.location.origin
      : 'https://shopsoma.com');
  const rawTitle =
    options?.title ?? (typeof document !== 'undefined' ? document.title : '') ?? 'ShopSoma';
  const rawReferrer =
    options?.referrer ?? (typeof document !== 'undefined' ? document.referrer : '');

  captureNavigationContext({ pathname, search, referrer: rawReferrer, origin });

  const measurementId = getConfiguredGaMeasurementId(options?.measurementId);
  if (!measurementId || !canUseCookieCategory('analytics')) {
    return false;
  }

  const initialized = initializeGoogleAnalytics({
    measurementId,
    debugMode: options?.debugMode,
  });
  if (!initialized) {
    return false;
  }

  const sanitized = sanitizeAnalyticsUrl(
    `${pathname}${search}`,
    origin,
    pendingLandingAttribution,
  );
  const deduplicationKey = `${measurementId}:${sanitized.locationKey}`;

  if (lastTrackedLocationKey === deduplicationKey) {
    return false;
  }

  const pageTitle = redactPersonalInfoFromText(rawTitle).trim() || 'ShopSoma';
  const pageReferrer = !hasSentInitialPageView
    ? pendingExternalReferrer ?? sanitizeReferrerUrl(rawReferrer, origin)
    : lastTrackedCleanLocation ?? undefined;

  const debugMode = isGaDebugModeEnabled(search, options?.debugMode);
  const gtag = ensureGtagFunction();

  if (hasCampaignAttribution(sanitized.attribution)) {
    activeCampaignAttribution = { ...sanitized.attribution };
    applyCampaignToGtag(gtag, sanitized.attribution);
  }

  gtag('set', {
    page_location: sanitized.pageLocation,
    page_path: sanitized.pagePath,
    page_title: pageTitle,
    ...(pageReferrer ? { page_referrer: pageReferrer } : {}),
  });

  const eventPayload: Record<string, string | boolean> = {
    send_to: measurementId,
    page_location: sanitized.pageLocation,
    page_path: sanitized.pagePath,
    page_title: pageTitle,
  };

  if (pageReferrer) {
    eventPayload.page_referrer = pageReferrer;
  }

  if (sanitized.attribution.utm_source) {
    eventPayload.campaign_source = sanitized.attribution.utm_source;
    eventPayload.utm_source = sanitized.attribution.utm_source;
  }
  if (sanitized.attribution.utm_medium) {
    eventPayload.campaign_medium = sanitized.attribution.utm_medium;
    eventPayload.utm_medium = sanitized.attribution.utm_medium;
  }
  if (sanitized.attribution.utm_campaign) {
    eventPayload.campaign_name = sanitized.attribution.utm_campaign;
    eventPayload.utm_campaign = sanitized.attribution.utm_campaign;
  }
  if (sanitized.attribution.utm_content) {
    eventPayload.campaign_content = sanitized.attribution.utm_content;
    eventPayload.utm_content = sanitized.attribution.utm_content;
  }
  if (sanitized.attribution.utm_term) {
    eventPayload.campaign_term = sanitized.attribution.utm_term;
    eventPayload.utm_term = sanitized.attribution.utm_term;
  }
  if (sanitized.attribution.utm_id) {
    eventPayload.campaign_id = sanitized.attribution.utm_id;
    eventPayload.utm_id = sanitized.attribution.utm_id;
  }

  if (debugMode) {
    eventPayload.debug_mode = true;
  }

  gtag('event', 'page_view', eventPayload);

  lastTrackedLocationKey = deduplicationKey;
  lastTrackedCleanLocation = sanitized.cleanPageLocation;
  pendingLandingAttribution = null;
  pendingExternalReferrer = undefined;
  hasSentInitialPageView = true;

  return true;
}

export function trackAnalyticsEvent(
  eventName: string,
  params?: Record<string, unknown>,
  options?: { measurementId?: string; debugMode?: boolean },
): boolean {
  if (typeof window === 'undefined') return false;
  const trimmedEventName = eventName.trim();
  if (!trimmedEventName) return false;

  const measurementId = getConfiguredGaMeasurementId(options?.measurementId);
  if (!measurementId || !canUseCookieCategory('analytics')) {
    return false;
  }

  const initialized = initializeGoogleAnalytics({
    measurementId,
    debugMode: options?.debugMode,
  });
  if (!initialized) {
    return false;
  }

  const sanitizedParams = sanitizeEventParameters(params);
  const debugMode = isGaDebugModeEnabled(undefined, options?.debugMode);
  const gtag = ensureGtagFunction();

  gtag('event', trimmedEventName, {
    send_to: measurementId,
    ...sanitizedParams,
    ...(debugMode ? { debug_mode: true } : {}),
  });

  return true;
}

export function syncAnalyticsWithConsent(options?: TrackPageViewOptions): void {
  if (typeof window === 'undefined') return;

  if (!canUseCookieCategory('analytics')) {
    deactivateGoogleAnalytics(options?.measurementId);
    return;
  }

  initializeGoogleAnalytics({
    measurementId: options?.measurementId,
    debugMode: options?.debugMode,
  });
  trackPageView(options);
}

export function bindAnalyticsConsentListener(
  getCurrentRouteOptions?: () => TrackPageViewOptions | undefined,
): () => void {
  if (consentSubscriptionCleanup) {
    consentSubscriptionCleanup();
    consentSubscriptionCleanup = null;
  }

  const handleStateChange = () => {
    const routeOptions = getCurrentRouteOptions?.();
    if (!canUseCookieCategory('analytics')) {
      deactivateGoogleAnalytics(routeOptions?.measurementId);
      return;
    }

    initializeGoogleAnalytics({
      measurementId: routeOptions?.measurementId,
      debugMode: routeOptions?.debugMode,
    });
    trackPageView(routeOptions);
  };

  const unsubscribeStore = useCookieConsentStore.subscribe(handleStateChange);
  const handleWindowConsentEvent = () => handleStateChange();

  if (typeof window !== 'undefined') {
    window.addEventListener('shopsoma:cookie-consent-changed', handleWindowConsentEvent);
  }

  const cleanup = () => {
    unsubscribeStore();
    if (typeof window !== 'undefined') {
      window.removeEventListener('shopsoma:cookie-consent-changed', handleWindowConsentEvent);
    }
    if (consentSubscriptionCleanup === cleanup) {
      consentSubscriptionCleanup = null;
    }
  };

  consentSubscriptionCleanup = cleanup;
  return cleanup;
}

export function getActiveCampaignAttribution(): CampaignAttribution {
  return { ...activeCampaignAttribution };
}

export function resetGoogleAnalyticsForTests(): void {
  if (consentSubscriptionCleanup) {
    consentSubscriptionCleanup();
    consentSubscriptionCleanup = null;
  }

  if (typeof window !== 'undefined') {
    if (initializedMeasurementId) {
      delete window[`ga-disable-${initializedMeasurementId}`];
    }
    delete window.gtag;
    delete window.dataLayer;
  }

  if (typeof document !== 'undefined') {
    document.getElementById(GA_SCRIPT_ID)?.remove();
  }

  initializedMeasurementId = null;
  lastTrackedLocationKey = null;
  lastTrackedCleanLocation = null;
  pendingLandingAttribution = null;
  activeCampaignAttribution = {};
  pendingExternalReferrer = undefined;
  hasSentInitialPageView = false;
  sessionDebugMode = false;
}
