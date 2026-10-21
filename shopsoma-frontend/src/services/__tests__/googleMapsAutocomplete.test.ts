import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  ensureGoogleMapsPlacesLoaded,
  fetchAddressSuggestions,
  normalizeCountryName,
  normalizeNigerianState,
  normalizePlaceToAddress,
  normalizePostalCode,
  resetGoogleMapsLoaderForTests,
  resolveAddressSuggestion,
} from '../googleMapsAutocomplete';

describe('googleMapsAutocomplete', () => {
  beforeEach(() => {
    resetGoogleMapsLoaderForTests();
    delete window.google;
    document.getElementById('google-maps-places-sdk')?.remove();
  });

  afterEach(() => {
    resetGoogleMapsLoaderForTests();
    delete window.google;
    document.getElementById('google-maps-places-sdk')?.remove();
  });

  describe('normalizeNigerianState', () => {
    it('normalizes Google Maps state suffixes and FCT aliases to NIGERIA_STATES values', () => {
      expect(normalizeNigerianState('Lagos State')).toBe('Lagos');
      expect(normalizeNigerianState('Rivers State')).toBe('Rivers');
      expect(normalizeNigerianState('State of Osun')).toBe('Osun');
      expect(normalizeNigerianState('FCT')).toBe('Federal Capital Territory');
      expect(normalizeNigerianState('Abuja')).toBe('Federal Capital Territory');
      expect(normalizeNigerianState('Federal Capital Territory (FCT)')).toBe('Federal Capital Territory');
      expect(normalizeNigerianState('Nassarawa State')).toBe('Nasarawa');
      expect(normalizeNigerianState('Akwa-Ibom State')).toBe('Akwa Ibom');
      expect(normalizeNigerianState('Cross-River')).toBe('Cross River');
    });

    it('falls back to formatted address segments when administrative_area_level_1 is missing', () => {
      expect(
        normalizeNigerianState('', '14 Wuse II, Abuja 900288, Nigeria')
      ).toBe('Federal Capital Territory');
      expect(
        normalizeNigerianState(undefined, '12 Admiralty Way, Lekki Phase 1, Lagos 106104, Nigeria')
      ).toBe('Lagos');
    });
  });

  describe('normalizeCountryName and normalizePostalCode', () => {
    it('normalizes country codes and names to Nigeria', () => {
      expect(normalizeCountryName('NG')).toBe('Nigeria');
      expect(normalizeCountryName('nigeria')).toBe('Nigeria');
      expect(normalizeCountryName('Federal Republic of Nigeria')).toBe('Nigeria');
      expect(normalizeCountryName('')).toBe('Nigeria');
    });

    it('normalizes postal codes and extracts 6-digit codes from formatted addresses', () => {
      expect(normalizePostalCode(' 100001 ')).toBe('100001');
      expect(normalizePostalCode('123456789012345')).toBe('123456789012');
      expect(normalizePostalCode('', '12 Admiralty Way, Lekki, Lagos 106104, Nigeria')).toBe('106104');
    });
  });

  describe('normalizePlaceToAddress', () => {
    it('extracts normalized street, city, Nigerian state, postal code, country, and coordinates', () => {
      const place = {
        place_id: 'place-lekki-12',
        formatted_address: '12 Admiralty Way, Lekki Phase 1, Lagos 106104, Nigeria',
        address_components: [
          { long_name: '12', short_name: '12', types: ['street_number'] },
          { long_name: 'Admiralty Way', short_name: 'Admiralty Way', types: ['route'] },
          { long_name: 'Lekki Phase 1', short_name: 'Lekki Phase 1', types: ['sublocality_level_1', 'sublocality'] },
          { long_name: 'Lagos', short_name: 'Lagos', types: ['locality'] },
          { long_name: 'Lagos State', short_name: 'LA', types: ['administrative_area_level_1'] },
          { long_name: '106104', short_name: '106104', types: ['postal_code'] },
          { long_name: 'Nigeria', short_name: 'NG', types: ['country'] },
        ],
        geometry: {
          location: {
            lat: () => 6.4474,
            lng: () => 3.4723,
          },
        },
      };

      const normalized = normalizePlaceToAddress(place, {
        placeId: 'place-lekki-12',
        mainText: '12 Admiralty Way',
        secondaryText: 'Lekki Phase 1, Lagos, Nigeria',
        description: '12 Admiralty Way, Lekki Phase 1, Lagos, Nigeria',
      });

      expect(normalized).toEqual({
        placeId: 'place-lekki-12',
        formattedAddress: '12 Admiralty Way, Lekki Phase 1, Lagos 106104, Nigeria',
        addressLine1: '12 Admiralty Way',
        addressLine2: undefined,
        city: 'Lagos',
        state: 'Lagos',
        postalCode: '106104',
        country: 'Nigeria',
        latitude: 6.4474,
        longitude: 3.4723,
      });
    });

    it('preserves suggestion house number when Google route component omits street_number', () => {
      const place = {
        place_id: 'place-awolowo-15',
        formatted_address: 'Awolowo Rd, Ikoyi, Lagos, Nigeria',
        address_components: [
          { long_name: 'Awolowo Road', short_name: 'Awolowo Rd', types: ['route'] },
          { long_name: 'Ikoyi', short_name: 'Ikoyi', types: ['sublocality_level_1'] },
          { long_name: 'Eti-Osa Local Government Area', short_name: 'Eti-Osa', types: ['administrative_area_level_2'] },
          { long_name: 'Lagos State', short_name: 'LA', types: ['administrative_area_level_1'] },
          { long_name: 'Nigeria', short_name: 'NG', types: ['country'] },
        ],
      };

      const normalized = normalizePlaceToAddress(place, {
        placeId: 'place-awolowo-15',
        mainText: '15 Awolowo Road',
        secondaryText: 'Ikoyi, Lagos, Nigeria',
        description: '15 Awolowo Road, Ikoyi, Lagos, Nigeria',
      });

      expect(normalized.addressLine1).toBe('15 Awolowo Road');
      expect(normalized.city).toBe('Ikoyi');
      expect(normalized.state).toBe('Lagos');
      expect(normalized.country).toBe('Nigeria');
    });
  });

  describe('fetchAddressSuggestions and resolveAddressSuggestion', () => {
    it('fetches predictions restricted to Nigeria and resolves normalized place details', async () => {
      const getPlacePredictions = vi.fn((_request, callback) => {
        callback(
          [
            {
              place_id: 'place-abuja-1',
              description: '24 Aminu Kano Crescent, Wuse 2, Abuja, Nigeria',
              structured_formatting: {
                main_text: '24 Aminu Kano Crescent',
                secondary_text: 'Wuse 2, Abuja, Nigeria',
              },
            },
          ],
          'OK'
        );
      });
      const getDetails = vi.fn((_request, callback) => {
        callback(
          {
            place_id: 'place-abuja-1',
            formatted_address: '24 Aminu Kano Cres, Wuse 2, Abuja 900288, Federal Capital Territory, Nigeria',
            address_components: [
              { long_name: '24', short_name: '24', types: ['street_number'] },
              { long_name: 'Aminu Kano Crescent', short_name: 'Aminu Kano Cres', types: ['route'] },
              { long_name: 'Abuja', short_name: 'Abuja', types: ['locality'] },
              { long_name: 'Federal Capital Territory', short_name: 'FCT', types: ['administrative_area_level_1'] },
              { long_name: '900288', short_name: '900288', types: ['postal_code'] },
              { long_name: 'Nigeria', short_name: 'NG', types: ['country'] },
            ],
          },
          'OK'
        );
      });

      window.google = {
        maps: {
          places: {
            PlacesServiceStatus: { OK: 'OK', ZERO_RESULTS: 'ZERO_RESULTS' },
            AutocompleteService: function () {
              return { getPlacePredictions };
            },
            PlacesService: function () {
              return { getDetails };
            },
          },
        },
      };

      const suggestions = await fetchAddressSuggestions('24 Aminu Kano');
      expect(getPlacePredictions).toHaveBeenCalledWith(
        {
          input: '24 Aminu Kano',
          componentRestrictions: { country: 'ng' },
        },
        expect.any(Function)
      );
      expect(suggestions).toEqual([
        {
          placeId: 'place-abuja-1',
          mainText: '24 Aminu Kano Crescent',
          secondaryText: 'Wuse 2, Abuja, Nigeria',
          description: '24 Aminu Kano Crescent, Wuse 2, Abuja, Nigeria',
          placePrediction: undefined,
        },
      ]);

      const resolved = await resolveAddressSuggestion(suggestions[0]);
      expect(resolved).toMatchObject({
        placeId: 'place-abuja-1',
        addressLine1: '24 Aminu Kano Crescent',
        city: 'Abuja',
        state: 'Federal Capital Territory',
        postalCode: '900288',
        country: 'Nigeria',
      });
    });

    it('returns an empty list on ZERO_RESULTS and throws on service failure or missing API key', async () => {
      await expect(ensureGoogleMapsPlacesLoaded('')).rejects.toThrow(/VITE_GOOGLE_MAPS_API_KEY/i);

      window.google = {
        maps: {
          places: {
            PlacesServiceStatus: { OK: 'OK', ZERO_RESULTS: 'ZERO_RESULTS' },
            AutocompleteService: function () {
              return {
                getPlacePredictions: (_req: any, cb: any) => cb(null, 'ZERO_RESULTS'),
              };
            },
          },
        },
      };

      expect(await fetchAddressSuggestions('Unknown street')).toEqual([]);
    });

    it('supports Places API (New) structuredFormat suggestions and latitude/longitude details', async () => {
      const fetchAutocompleteSuggestions = vi.fn().mockResolvedValue({
        suggestions: [
          {
            placePrediction: {
              placeId: 'ChIJLdsYFv70OxARcc7GAnFaa38',
              text: { text: '12 Admiralty Way, Lekki, Nigeria' },
              structuredFormat: {
                mainText: { text: '12 Admiralty Way' },
                secondaryText: { text: 'Lekki, Nigeria' },
              },
              toPlace: () => ({
                id: 'ChIJLdsYFv70OxARcc7GAnFaa38',
                formattedAddress: '12 Admiralty Wy, Lekki Phase 1, Lekki 106104, Lagos, Nigeria',
                addressComponents: [
                  { longText: '12', shortText: '12', types: ['street_number'] },
                  { longText: 'Admiralty Way', shortText: 'Admiralty Wy', types: ['route'] },
                  { longText: 'Lekki', shortText: 'Lekki', types: ['locality'] },
                  { longText: 'Lagos', shortText: 'LA', types: ['administrative_area_level_1'] },
                  { longText: '106104', shortText: '106104', types: ['postal_code'] },
                  { longText: 'Nigeria', shortText: 'NG', types: ['country'] },
                ],
                location: { latitude: 6.4396331, longitude: 3.45613 },
                fetchFields: vi.fn().mockResolvedValue(undefined),
              }),
            },
          },
        ],
      });

      window.google = {
        maps: {
          places: {
            AutocompleteSuggestion: { fetchAutocompleteSuggestions },
          },
        },
      };

      const suggestions = await fetchAddressSuggestions('12 Admiralty Way');
      expect(suggestions).toHaveLength(1);
      expect(suggestions[0]).toMatchObject({
        placeId: 'ChIJLdsYFv70OxARcc7GAnFaa38',
        mainText: '12 Admiralty Way',
        secondaryText: 'Lekki, Nigeria',
        description: '12 Admiralty Way, Lekki, Nigeria',
      });

      const resolved = await resolveAddressSuggestion(suggestions[0]);
      expect(resolved).toEqual({
        placeId: 'ChIJLdsYFv70OxARcc7GAnFaa38',
        formattedAddress: '12 Admiralty Wy, Lekki Phase 1, Lekki 106104, Lagos, Nigeria',
        addressLine1: '12 Admiralty Way',
        addressLine2: undefined,
        city: 'Lekki',
        state: 'Lagos',
        postalCode: '106104',
        country: 'Nigeria',
        latitude: 6.4396331,
        longitude: 3.45613,
      });
    });
  });
});
