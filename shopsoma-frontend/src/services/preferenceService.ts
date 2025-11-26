import api from './api';

export interface PreferenceData {
  interest: string | null;
  preferredLanguage: string | null;
  preferredCurrency: string | null;
  favoriteDesigners: string[];
  favoriteCategories: string[];
}

export interface PreferenceUpdatePayload {
  interest: string | null;
  preferredLanguage: string | null;
  preferredCurrency: string | null;
  favoriteDesigners: string[];
  favoriteCategories: string[];
}

export interface PreferenceOption {
  id: string;
  name: string;
  slug?: string | null;
}

export interface PreferenceOptionsResponse {
  designers: PreferenceOption[];
  categories: PreferenceOption[];
}

const mapResponse = (data: any): PreferenceData => ({
  interest: data?.interest ?? null,
  preferredLanguage: data?.preferred_language ?? null,
  preferredCurrency: data?.preferred_currency ?? null,
  favoriteDesigners: data?.favorite_designers ?? [],
  favoriteCategories: data?.favorite_categories ?? [],
});

export async function getPreferences(): Promise<PreferenceData> {
  const response = await api.get('/preferences');
  return mapResponse(response.data);
}

export async function updatePreferences(payload: PreferenceUpdatePayload): Promise<PreferenceData> {
  const response = await api.put('/preferences', {
    interest: payload.interest,
    preferred_language: payload.preferredLanguage,
    preferred_currency: payload.preferredCurrency,
    favorite_designers: payload.favoriteDesigners,
    favorite_categories: payload.favoriteCategories,
  });
  return mapResponse(response.data);
}

export async function getPreferenceOptions(): Promise<PreferenceOptionsResponse> {
  const response = await api.get('/preferences/options');
  return {
    designers: response.data?.designers ?? [],
    categories: response.data?.categories ?? [],
  };
}
