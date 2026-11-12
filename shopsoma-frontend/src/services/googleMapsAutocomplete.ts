import { NIGERIA_STATES } from '../config/nigeriaStates';

declare global {
  interface Window {
    google?: any;
  }
}

export interface AddressSuggestion {
  placeId: string;
  mainText: string;
  secondaryText: string;
  description: string;
  placePrediction?: any;
}

export interface NormalizedGoogleAddress {
  placeId: string;
  formattedAddress: string;
  addressLine1: string;
  addressLine2?: string;
  city: string;
  state: string;
  postalCode: string;
  country: string;
  latitude?: number;
  longitude?: number;
}

export type GoogleMapsErrorCode =
  | 'missing_api_key'
  | 'script_load_error'
  | 'autocomplete_error'
  | 'place_details_error'
  | 'invalid_address_details';

export class GoogleMapsAutocompleteError extends Error {
  code: GoogleMapsErrorCode;

  constructor(message: string, code: GoogleMapsErrorCode) {
    super(message);
    this.name = 'GoogleMapsAutocompleteError';
    this.code = code;
  }
}

const GOOGLE_MAPS_SCRIPT_ID = 'google-maps-places-sdk';
let googleMapsLoadPromise: Promise<any> | null = null;

const STATE_ALIASES: Record<string, string> = {
  fct: 'Federal Capital Territory',
  'f c t': 'Federal Capital Territory',
  abuja: 'Federal Capital Territory',
  'abuja fct': 'Federal Capital Territory',
  'abuja federal capital territory': 'Federal Capital Territory',
  'federal capital territory': 'Federal Capital Territory',
  'federal capital territory fct': 'Federal Capital Territory',
  nassarawa: 'Nasarawa',
  'akwa ibom': 'Akwa Ibom',
  'cross river': 'Cross River',
};

function cleanStateToken(value: string): string {
  return value
    .toLowerCase()
    .replace(/[._()-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/^the\s+/, '')
    .replace(/^state\s+of\s+/, '')
    .replace(/\s+state$/, '')
    .trim();
}

export function normalizeNigerianState(rawState?: string, fallbackText?: string): string {
  const candidates: string[] = [];
  if (rawState && rawState.trim()) {
    candidates.push(rawState.trim());
  }
  if (fallbackText && fallbackText.trim()) {
    const segments = fallbackText
      .split(',')
      .map(segment => segment.trim())
      .filter(Boolean)
      .reverse();
    candidates.push(...segments);
  }

  for (const candidate of candidates) {
    const withoutPostal = candidate.replace(/\b\d{5,6}\b/g, ' ').trim();
    const cleaned = cleanStateToken(withoutPostal);
    if (!cleaned || cleaned === 'nigeria' || cleaned === 'ng') continue;

    if (STATE_ALIASES[cleaned]) {
      return STATE_ALIASES[cleaned];
    }

    const directMatch = NIGERIA_STATES.find(
      state => cleanStateToken(state) === cleaned
    );
    if (directMatch) {
      return directMatch;
    }

    for (const [alias, canonical] of Object.entries(STATE_ALIASES)) {
      const aliasRegex = new RegExp(`\\b${alias.replace(/\s+/g, '\\s+')}\\b`, 'i');
      if (aliasRegex.test(cleaned)) {
        return canonical;
      }
    }

    const containedMatch = NIGERIA_STATES.find(state => {
      const token = cleanStateToken(state).replace(/\s+/g, '\\s+');
      return new RegExp(`\\b${token}\\b`, 'i').test(cleaned);
    });
    if (containedMatch) {
      return containedMatch;
    }
  }

  return '';
}

const COUNTRY_ALIASES: Record<string, { name: string; iso2: string }> = {
  ng: { name: 'Nigeria', iso2: 'ng' },
  nga: { name: 'Nigeria', iso2: 'ng' },
  nigeria: { name: 'Nigeria', iso2: 'ng' },
  'federal republic of nigeria': { name: 'Nigeria', iso2: 'ng' },
  gh: { name: 'Ghana', iso2: 'gh' },
  gha: { name: 'Ghana', iso2: 'gh' },
  ghana: { name: 'Ghana', iso2: 'gh' },
  'republic of ghana': { name: 'Ghana', iso2: 'gh' },
  us: { name: 'United States', iso2: 'us' },
  usa: { name: 'United States', iso2: 'us' },
  'u s': { name: 'United States', iso2: 'us' },
  'u s a': { name: 'United States', iso2: 'us' },
  'united states': { name: 'United States', iso2: 'us' },
  'united states of america': { name: 'United States', iso2: 'us' },
  gb: { name: 'United Kingdom', iso2: 'gb' },
  gbr: { name: 'United Kingdom', iso2: 'gb' },
  uk: { name: 'United Kingdom', iso2: 'gb' },
  'u k': { name: 'United Kingdom', iso2: 'gb' },
  'united kingdom': { name: 'United Kingdom', iso2: 'gb' },
  'united kingdom of great britain and northern ireland': { name: 'United Kingdom', iso2: 'gb' },
  'great britain': { name: 'United Kingdom', iso2: 'gb' },
  england: { name: 'United Kingdom', iso2: 'gb' },
  scotland: { name: 'United Kingdom', iso2: 'gb' },
  wales: { name: 'United Kingdom', iso2: 'gb' },
  'northern ireland': { name: 'United Kingdom', iso2: 'gb' },
  ca: { name: 'Canada', iso2: 'ca' },
  can: { name: 'Canada', iso2: 'ca' },
  canada: { name: 'Canada', iso2: 'ca' },
  za: { name: 'South Africa', iso2: 'za' },
  zaf: { name: 'South Africa', iso2: 'za' },
  'south africa': { name: 'South Africa', iso2: 'za' },
  'republic of south africa': { name: 'South Africa', iso2: 'za' },
  ke: { name: 'Kenya', iso2: 'ke' },
  ken: { name: 'Kenya', iso2: 'ke' },
  kenya: { name: 'Kenya', iso2: 'ke' },
  'republic of kenya': { name: 'Kenya', iso2: 'ke' },
  ae: { name: 'United Arab Emirates', iso2: 'ae' },
  are: { name: 'United Arab Emirates', iso2: 'ae' },
  uae: { name: 'United Arab Emirates', iso2: 'ae' },
  'u a e': { name: 'United Arab Emirates', iso2: 'ae' },
  'united arab emirates': { name: 'United Arab Emirates', iso2: 'ae' },
  fr: { name: 'France', iso2: 'fr' },
  fra: { name: 'France', iso2: 'fr' },
  france: { name: 'France', iso2: 'fr' },
  'french republic': { name: 'France', iso2: 'fr' },
  de: { name: 'Germany', iso2: 'de' },
  deu: { name: 'Germany', iso2: 'de' },
  germany: { name: 'Germany', iso2: 'de' },
  'federal republic of germany': { name: 'Germany', iso2: 'de' },
};

function cleanCountryToken(value: string): string {
  return value
    .toLowerCase()
    .replace(/[._()-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

export function detectCountryCodeFromQuery(query: string): string | null {
  const segments = query
    .split(',')
    .map(segment => cleanCountryToken(segment))
    .filter(Boolean);
  for (let i = segments.length - 1; i >= 0; i -= 1) {
    const match = COUNTRY_ALIASES[segments[i]];
    if (match) {
      return match.iso2;
    }
  }
  const cleanedFull = cleanCountryToken(query);
  for (const [alias, entry] of Object.entries(COUNTRY_ALIASES)) {
    if (alias.length < 3 && alias !== 'uk' && alias !== 'us') continue;
    const regex = new RegExp(`(?:^|\\s)${alias.replace(/\s+/g, '\\s+')}$`, 'i');
    if (regex.test(cleanedFull)) {
      return entry.iso2;
    }
  }
  return null;
}

export function normalizeCountryName(rawCountry?: string, fallbackText?: string): string {
  const cleaned = (rawCountry || '').trim();
  if (cleaned) {
    const token = cleanCountryToken(cleaned);
    if (COUNTRY_ALIASES[token]) {
      return COUNTRY_ALIASES[token].name;
    }
    return cleaned;
  }
  if (fallbackText && fallbackText.trim()) {
    const segments = fallbackText
      .split(',')
      .map(segment => segment.trim())
      .filter(Boolean);
    for (let i = segments.length - 1; i >= 0; i -= 1) {
      const token = cleanCountryToken(segments[i]);
      if (COUNTRY_ALIASES[token]) {
        return COUNTRY_ALIASES[token].name;
      }
    }
  }
  return 'Nigeria';
}

export function normalizePostalCode(rawPostalCode?: string, fallbackAddress?: string): string {
  const direct = (rawPostalCode || '').trim();
  if (direct) {
    return direct.slice(0, 12);
  }
  if (fallbackAddress) {
    const match = /\b(\d{6})\b/.exec(fallbackAddress);
    if (match) {
      return match[1];
    }
  }
  return '';
}

interface ParsedComponent {
  longName: string;
  shortName: string;
  types: string[];
}

function parseAddressComponents(rawComponents: any[] | undefined): ParsedComponent[] {
  if (!Array.isArray(rawComponents)) return [];
  return rawComponents.map(component => ({
    longName: String(component?.long_name ?? component?.longText ?? '').trim(),
    shortName: String(component?.short_name ?? component?.shortText ?? '').trim(),
    types: Array.isArray(component?.types) ? component.types : [],
  }));
}

function findComponent(components: ParsedComponent[], ...types: string[]): ParsedComponent | undefined {
  for (const type of types) {
    const match = components.find(component => component.types.includes(type) && (component.longName || component.shortName));
    if (match) return match;
  }
  return undefined;
}

function cleanAdminAreaCity(value: string): string {
  return value
    .replace(/\s+Local Government Area$/i, '')
    .replace(/\s+L\.?G\.?A\.?$/i, '')
    .replace(/\s+Municipal Area Council$/i, '')
    .trim();
}

export function normalizePlaceToAddress(
  place: any,
  suggestion?: AddressSuggestion,
  options?: { country?: string }
): NormalizedGoogleAddress {
  const components = parseAddressComponents(place?.address_components ?? place?.addressComponents);
  const formattedAddress = String(
    place?.formatted_address ??
    place?.formattedAddress ??
    suggestion?.description ??
    ''
  ).trim();

  const streetNumber = findComponent(components, 'street_number')?.longName || '';
  const route = findComponent(components, 'route')?.longName || '';
  const premise = findComponent(components, 'premise')?.longName || '';
  const subpremise = findComponent(components, 'subpremise')?.longName || '';
  const establishment = findComponent(components, 'establishment', 'point_of_interest')?.longName || '';
  const neighborhood = findComponent(components, 'neighborhood')?.longName || '';
  const sublocality = findComponent(components, 'sublocality_level_1', 'sublocality')?.longName || '';
  const locality = findComponent(components, 'locality', 'postal_town')?.longName || '';
  const adminArea2 = cleanAdminAreaCity(
    findComponent(components, 'administrative_area_level_2')?.longName || ''
  );
  const adminArea1Component = findComponent(components, 'administrative_area_level_1');
  const countryComponent = findComponent(components, 'country');
  const postalCodeComponent = findComponent(components, 'postal_code');

  const suggestionMainText = suggestion?.mainText?.trim() || '';
  const firstFormattedSegment = formattedAddress.split(',')[0]?.trim() || '';

  let addressLine1 = '';
  if (streetNumber && route) {
    addressLine1 = `${streetNumber} ${route}`.trim();
  } else if (route) {
    if (
      suggestionMainText &&
      suggestionMainText.toLowerCase().includes(route.toLowerCase()) &&
      suggestionMainText.length > route.length
    ) {
      addressLine1 = suggestionMainText;
    } else if (premise && !route.toLowerCase().includes(premise.toLowerCase())) {
      addressLine1 = `${premise}, ${route}`;
    } else {
      addressLine1 = route;
    }
  } else if (premise) {
    addressLine1 = sublocality && !premise.toLowerCase().includes(sublocality.toLowerCase())
      ? `${premise}, ${sublocality}`
      : premise;
  } else if (establishment) {
    addressLine1 = establishment;
  } else if (suggestionMainText) {
    addressLine1 = suggestionMainText;
  } else if (firstFormattedSegment) {
    addressLine1 = firstFormattedSegment;
  }

  const country = normalizeCountryName(
    countryComponent?.longName || countryComponent?.shortName,
    formattedAddress || suggestion?.secondaryText || options?.country
  );
  const isNigeria = country.toLowerCase() === 'nigeria';

  let state = isNigeria
    ? normalizeNigerianState(
        adminArea1Component?.longName || adminArea1Component?.shortName,
        formattedAddress || suggestion?.secondaryText
      )
    : (
        adminArea1Component?.longName ||
        adminArea1Component?.shortName ||
        adminArea2 ||
        locality ||
        sublocality ||
        ''
      ).trim();

  let city = locality || sublocality || adminArea2 || neighborhood;
  if ((!city || (!isNigeria && !state)) && (suggestion?.secondaryText || formattedAddress)) {
    const fallbackSource = suggestion?.secondaryText || formattedAddress;
    const segments = fallbackSource
      .split(',')
      .map(segment => segment.replace(/\b\d{5,6}\b/g, '').trim())
      .filter(Boolean);

    const nonCountrySegments = segments.filter(segment => {
      const token = cleanCountryToken(segment);
      if (!token) return false;
      if (COUNTRY_ALIASES[token]) return false;
      if (token === cleanCountryToken(country)) return false;
      if (addressLine1 && token === cleanCountryToken(addressLine1)) return false;
      return true;
    });

    if (!city) {
      const candidateCity = nonCountrySegments.find(segment => {
        if (state && cleanStateToken(segment) === cleanStateToken(state)) return false;
        return true;
      });
      if (candidateCity) {
        city = candidateCity;
      }
    }

    if (!isNigeria && !state) {
      const candidateState = [...nonCountrySegments].reverse().find(segment => {
        if (city && cleanStateToken(segment) === cleanStateToken(city)) return false;
        return true;
      });
      state = candidateState || city || '';
    }
  }
  if (!city && state) {
    city = isNigeria && state === 'Federal Capital Territory' ? 'Abuja' : state;
  }
  if (!isNigeria && !state && city) {
    state = city;
  }

  const postalCode = normalizePostalCode(postalCodeComponent?.longName, formattedAddress);

  const rawLat =
    place?.geometry?.location?.lat ??
    place?.location?.lat ??
    place?.location?.latitude;
  const rawLng =
    place?.geometry?.location?.lng ??
    place?.location?.lng ??
    place?.location?.longitude;
  const latitude = typeof rawLat === 'function' ? rawLat() : typeof rawLat === 'number' ? rawLat : undefined;
  const longitude = typeof rawLng === 'function' ? rawLng() : typeof rawLng === 'number' ? rawLng : undefined;

  return {
    placeId: String(place?.place_id ?? place?.id ?? suggestion?.placeId ?? '').trim(),
    formattedAddress: formattedAddress || [addressLine1, city, state, country].filter(Boolean).join(', '),
    addressLine1,
    addressLine2: subpremise || undefined,
    city,
    state,
    postalCode,
    country,
    latitude: Number.isFinite(latitude) ? latitude : undefined,
    longitude: Number.isFinite(longitude) ? longitude : undefined,
  };
}

export function resetGoogleMapsLoaderForTests(): void {
  googleMapsLoadPromise = null;
}

function getConfiguredGoogleMapsApiKey(explicitApiKey?: string): string {
  return (explicitApiKey ?? import.meta.env.VITE_GOOGLE_MAPS_API_KEY ?? '')
    .trim()
    .replace(/^['"]|['"]$/g, '');
}

export function ensureGoogleMapsPlacesLoaded(explicitApiKey?: string): Promise<any> {
  if (typeof window === 'undefined') {
    return Promise.reject(
      new GoogleMapsAutocompleteError('Google Maps is unavailable in this environment.', 'script_load_error')
    );
  }

  if (window.google?.maps?.places) {
    return Promise.resolve(window.google.maps.places);
  }

  if (googleMapsLoadPromise) {
    return googleMapsLoadPromise;
  }

  const apiKey = getConfiguredGoogleMapsApiKey(explicitApiKey);
  if (!apiKey) {
    return Promise.reject(
      new GoogleMapsAutocompleteError(
        'Google Maps address verification is unavailable because VITE_GOOGLE_MAPS_API_KEY is not configured.',
        'missing_api_key'
      )
    );
  }

  googleMapsLoadPromise = new Promise((resolve, reject) => {
    if (window.google?.maps?.places) {
      resolve(window.google.maps.places);
      return;
    }

    const existingScript = document.getElementById(GOOGLE_MAPS_SCRIPT_ID) as HTMLScriptElement | null;
    if (existingScript) {
      existingScript.addEventListener('load', () => {
        if (window.google?.maps?.places) {
          resolve(window.google.maps.places);
        } else {
          googleMapsLoadPromise = null;
          reject(
            new GoogleMapsAutocompleteError(
              'Google Maps Places library did not initialize properly.',
              'script_load_error'
            )
          );
        }
      });
      existingScript.addEventListener('error', () => {
        googleMapsLoadPromise = null;
        existingScript.remove();
        reject(
          new GoogleMapsAutocompleteError(
            'Could not load Google Maps address autocomplete. Check your connection and retry.',
            'script_load_error'
          )
        );
      });
      return;
    }

    const script = document.createElement('script');
    script.id = GOOGLE_MAPS_SCRIPT_ID;
    script.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(apiKey)}&libraries=places&v=weekly`;
    script.async = true;
    script.defer = true;
    script.onload = () => {
      if (window.google?.maps?.places) {
        resolve(window.google.maps.places);
      } else {
        googleMapsLoadPromise = null;
        script.remove();
        reject(
          new GoogleMapsAutocompleteError(
            'Google Maps Places library did not initialize properly.',
            'script_load_error'
          )
        );
      }
    };
    script.onerror = () => {
      googleMapsLoadPromise = null;
      script.remove();
      reject(
        new GoogleMapsAutocompleteError(
          'Could not load Google Maps address autocomplete. Check your connection and retry.',
          'script_load_error'
        )
      );
    };
    document.head.appendChild(script);
  });

  return googleMapsLoadPromise;
}

function mapPredictionToSuggestion(prediction: any): AddressSuggestion {
  const description = String(
    prediction?.description ??
    prediction?.placePrediction?.text?.text ??
    ''
  ).trim();
  const mainText = String(
    prediction?.structured_formatting?.main_text ??
    prediction?.placePrediction?.mainText?.text ??
    prediction?.placePrediction?.structuredFormat?.mainText?.text ??
    description.split(',')[0] ??
    ''
  ).trim();
  const secondaryText = String(
    prediction?.structured_formatting?.secondary_text ??
    prediction?.placePrediction?.secondaryText?.text ??
    prediction?.placePrediction?.structuredFormat?.secondaryText?.text ??
    description.split(',').slice(1).join(',').trim()
  ).trim();
  const placeId = String(
    prediction?.place_id ??
    prediction?.placeId ??
    prediction?.placePrediction?.placeId ??
    description
  ).trim();

  return {
    placeId,
    mainText: mainText || description,
    secondaryText,
    description: description || [mainText, secondaryText].filter(Boolean).join(', '),
    placePrediction: prediction?.placePrediction,
  };
}

async function fetchPlacesNewApiSuggestions(
  query: string,
  regionCodes: string[],
  apiKey: string
): Promise<AddressSuggestion[]> {
  let response: Response;
  try {
    response = await fetch('https://places.googleapis.com/v1/places:autocomplete', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Goog-Api-Key': apiKey,
      },
      body: JSON.stringify({
        input: query,
        includedRegionCodes: regionCodes,
      }),
    });
  } catch {
    throw new GoogleMapsAutocompleteError(
      'Unable to load Google Maps address suggestions right now. Please retry.',
      'autocomplete_error'
    );
  }

  if (!response.ok) {
    throw new GoogleMapsAutocompleteError(
      'Unable to load Google Maps address suggestions right now. Please retry.',
      'autocomplete_error'
    );
  }

  const data = await response.json();
  const suggestions = Array.isArray(data?.suggestions) ? data.suggestions : [];
  return suggestions
    .map(mapPredictionToSuggestion)
    .filter((item: AddressSuggestion) => Boolean(item.placeId && item.mainText));
}

async function fetchPlacesNewApiDetails(placeId: string, apiKey: string): Promise<any> {
  let response: Response;
  try {
    response = await fetch(
      `https://places.googleapis.com/v1/places/${encodeURIComponent(placeId)}`,
      {
        headers: {
          'X-Goog-Api-Key': apiKey,
          'X-Goog-FieldMask': 'id,formattedAddress,addressComponents,location,displayName',
        },
      }
    );
  } catch {
    throw new GoogleMapsAutocompleteError(
      'Could not verify details for the selected Google Maps address. Please try again.',
      'place_details_error'
    );
  }

  if (!response.ok) {
    throw new GoogleMapsAutocompleteError(
      'Could not verify details for the selected Google Maps address. Please try again.',
      'place_details_error'
    );
  }

  return response.json();
}

export async function fetchAddressSuggestions(
  input: string,
  options?: { country?: string; countries?: string[] }
): Promise<AddressSuggestion[]> {
  const query = input.trim();
  if (query.length < 2) {
    return [];
  }

  const requestedCountryCode = (options?.country || 'ng').toLowerCase();
  const detectedCountryCode = detectCountryCodeFromQuery(query);
  const countryCode =
    requestedCountryCode === 'ng' && detectedCountryCode
      ? detectedCountryCode
      : requestedCountryCode;
  const regionCodes =
    options?.countries && options.countries.length > 0
      ? detectedCountryCode
        ? [detectedCountryCode]
        : Array.from(new Set(options.countries.map(c => c.toLowerCase())))
      : [countryCode];

  const apiKey = getConfiguredGoogleMapsApiKey();
  const places = await ensureGoogleMapsPlacesLoaded();

  if (typeof places.AutocompleteSuggestion?.fetchAutocompleteSuggestions === 'function') {
    try {
      const requestPayload: Record<string, any> = {
        input: query,
        includedRegionCodes: regionCodes,
      };
      if (regionCodes.length > 1) {
        requestPayload.region = countryCode;
      }
      const response = await places.AutocompleteSuggestion.fetchAutocompleteSuggestions(requestPayload);
      const suggestions = Array.isArray(response?.suggestions) ? response.suggestions : [];
      return suggestions
        .map(mapPredictionToSuggestion)
        .filter((item: AddressSuggestion) => Boolean(item.placeId && item.mainText));
    } catch {
      if (apiKey) {
        return fetchPlacesNewApiSuggestions(query, regionCodes, apiKey);
      }
      throw new GoogleMapsAutocompleteError(
        'Unable to load Google Maps address suggestions right now. Please retry.',
        'autocomplete_error'
      );
    }
  }

  if (typeof places.AutocompleteService === 'function') {
    const service = new places.AutocompleteService();
    return new Promise<AddressSuggestion[]>((resolve, reject) => {
      service.getPlacePredictions(
        {
          input: query,
          componentRestrictions: { country: countryCode },
        },
        (predictions: any[] | null, status: string) => {
          const okStatus = places.PlacesServiceStatus?.OK ?? 'OK';
          const zeroResultsStatus = places.PlacesServiceStatus?.ZERO_RESULTS ?? 'ZERO_RESULTS';

          if (status === zeroResultsStatus || (!predictions && status === okStatus)) {
            resolve([]);
            return;
          }
          if (status !== okStatus || !Array.isArray(predictions)) {
            if (status === 'REQUEST_DENIED' && apiKey) {
              fetchPlacesNewApiSuggestions(query, regionCodes, apiKey).then(resolve, reject);
              return;
            }
            reject(
              new GoogleMapsAutocompleteError(
                'Unable to load Google Maps address suggestions right now. Please retry.',
                'autocomplete_error'
              )
            );
            return;
          }

          resolve(
            predictions
              .map(mapPredictionToSuggestion)
              .filter(item => Boolean(item.placeId && item.mainText))
          );
        }
      );
    });
  }

  if (apiKey) {
    return fetchPlacesNewApiSuggestions(query, regionCodes, apiKey);
  }

  throw new GoogleMapsAutocompleteError(
    'Google Maps Places Autocomplete service is not available.',
    'autocomplete_error'
  );
}

export async function resolveAddressSuggestion(
  suggestion: AddressSuggestion,
  options?: { country?: string }
): Promise<NormalizedGoogleAddress> {
  const apiKey = getConfiguredGoogleMapsApiKey();
  const places = await ensureGoogleMapsPlacesLoaded();

  let rawPlace: any = null;

  if (typeof suggestion.placePrediction?.toPlace === 'function') {
    try {
      const placeObj = suggestion.placePrediction.toPlace();
      await placeObj.fetchFields({
        fields: ['addressComponents', 'formattedAddress', 'location', 'displayName', 'id'],
      });
      rawPlace = placeObj;
    } catch {
      if (apiKey) {
        rawPlace = await fetchPlacesNewApiDetails(suggestion.placeId, apiKey);
      } else {
        throw new GoogleMapsAutocompleteError(
          'Could not verify details for the selected Google Maps address. Please try again.',
          'place_details_error'
        );
      }
    }
  } else if (typeof places.PlacesService === 'function') {
    const container = document.createElement('div');
    const service = new places.PlacesService(container);
    rawPlace = await new Promise<any>((resolve, reject) => {
      service.getDetails(
        {
          placeId: suggestion.placeId,
          fields: ['address_components', 'formatted_address', 'geometry', 'name', 'place_id'],
        },
        (placeResult: any, status: string) => {
          const okStatus = places.PlacesServiceStatus?.OK ?? 'OK';
          if (status !== okStatus || !placeResult) {
            if (status === 'REQUEST_DENIED' && apiKey) {
              fetchPlacesNewApiDetails(suggestion.placeId, apiKey).then(resolve, reject);
              return;
            }
            reject(
              new GoogleMapsAutocompleteError(
                'Could not verify details for the selected Google Maps address. Please try again.',
                'place_details_error'
              )
            );
            return;
          }
          resolve(placeResult);
        }
      );
    });
  } else if (apiKey) {
    rawPlace = await fetchPlacesNewApiDetails(suggestion.placeId, apiKey);
  } else {
    rawPlace = {
      place_id: suggestion.placeId,
      formatted_address: suggestion.description,
    };
  }

  const normalized = normalizePlaceToAddress(rawPlace, suggestion, options);

  if (!normalized.addressLine1 || !normalized.city || !normalized.state) {
    const isNigeria = normalized.country.toLowerCase() === 'nigeria';
    throw new GoogleMapsAutocompleteError(
      isNigeria
        ? 'Selected Google Maps suggestion is missing required street, city, or Nigerian state details. Please choose a more specific street address.'
        : 'Selected Google Maps suggestion is missing required street, city, or state/province details. Please choose a more specific street address.',
      'invalid_address_details'
    );
  }

  return normalized;
}
