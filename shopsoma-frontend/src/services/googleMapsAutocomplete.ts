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

export function normalizeCountryName(rawCountry?: string): string {
  const cleaned = (rawCountry || '').trim();
  if (!cleaned) return 'Nigeria';
  const lower = cleaned.toLowerCase();
  if (lower === 'ng' || lower === 'nga' || lower === 'nigeria' || lower === 'federal republic of nigeria') {
    return 'Nigeria';
  }
  return cleaned;
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
  suggestion?: AddressSuggestion
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

  const state = normalizeNigerianState(
    adminArea1Component?.longName || adminArea1Component?.shortName,
    formattedAddress || suggestion?.secondaryText
  );

  let city = locality || sublocality || adminArea2 || neighborhood;
  if (!city && (suggestion?.secondaryText || formattedAddress)) {
    const fallbackSource = suggestion?.secondaryText || formattedAddress;
    const segments = fallbackSource
      .split(',')
      .map(segment => segment.replace(/\b\d{5,6}\b/g, '').trim())
      .filter(Boolean);

    const candidateCity = segments.find(segment => {
      const lower = segment.toLowerCase();
      if (lower === 'nigeria' || lower === 'ng') return false;
      if (addressLine1 && lower === addressLine1.toLowerCase()) return false;
      if (state && cleanStateToken(segment) === cleanStateToken(state)) return false;
      return true;
    });
    if (candidateCity) {
      city = candidateCity;
    }
  }
  if (!city && state) {
    city = state === 'Federal Capital Territory' ? 'Abuja' : state;
  }

  const postalCode = normalizePostalCode(postalCodeComponent?.longName, formattedAddress);
  const country = normalizeCountryName(countryComponent?.longName || countryComponent?.shortName);

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
  countryCode: string,
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
        includedRegionCodes: [countryCode],
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
  options?: { country?: string }
): Promise<AddressSuggestion[]> {
  const query = input.trim();
  if (query.length < 2) {
    return [];
  }

  const countryCode = (options?.country || 'ng').toLowerCase();
  const apiKey = getConfiguredGoogleMapsApiKey();
  const places = await ensureGoogleMapsPlacesLoaded();

  if (typeof places.AutocompleteSuggestion?.fetchAutocompleteSuggestions === 'function') {
    try {
      const response = await places.AutocompleteSuggestion.fetchAutocompleteSuggestions({
        input: query,
        includedRegionCodes: [countryCode],
      });
      const suggestions = Array.isArray(response?.suggestions) ? response.suggestions : [];
      return suggestions
        .map(mapPredictionToSuggestion)
        .filter((item: AddressSuggestion) => Boolean(item.placeId && item.mainText));
    } catch {
      if (apiKey) {
        return fetchPlacesNewApiSuggestions(query, countryCode, apiKey);
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
              fetchPlacesNewApiSuggestions(query, countryCode, apiKey).then(resolve, reject);
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
    return fetchPlacesNewApiSuggestions(query, countryCode, apiKey);
  }

  throw new GoogleMapsAutocompleteError(
    'Google Maps Places Autocomplete service is not available.',
    'autocomplete_error'
  );
}

export async function resolveAddressSuggestion(
  suggestion: AddressSuggestion
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

  const normalized = normalizePlaceToAddress(rawPlace, suggestion);

  if (!normalized.addressLine1 || !normalized.city || !normalized.state) {
    throw new GoogleMapsAutocompleteError(
      'Selected Google Maps suggestion is missing required street, city, or Nigerian state details. Please choose a more specific street address.',
      'invalid_address_details'
    );
  }

  return normalized;
}
