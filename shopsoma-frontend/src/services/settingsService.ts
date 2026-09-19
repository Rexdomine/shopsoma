/**
 * Settings Service
 * API calls for application settings management
 */
import api from './api';

export interface ExchangeRate {
  rate: number;
  updated_at: string;
}

export interface Setting {
  id: string;
  key: string;
  value: string;
  description: string | null;
  created_at: string;
  updated_at: string;
}

export interface ExchangeRateUpdate {
  rate: number;
}

export interface ShippingProviderSettings {
  provider: 'manual' | 'shipbubble' | 'dhl';
  use_shipbubble: boolean;
  readiness: Record<'manual' | 'shipbubble' | 'dhl', boolean>;
  checkout_estimates_required: boolean;
}

export interface ShippingProviderUpdate {
  provider: 'manual' | 'shipbubble' | 'dhl';
  use_shipbubble?: boolean;
}

export interface PayoutHoldSettings {
  hold_days: number;
  updated_at?: string | null;
}

export interface PayoutHoldUpdate {
  hold_days: number;
}

export interface CommissionSettings {
  commission_rate: number;
  updated_at?: string | null;
}

export interface CommissionUpdate {
  commission_rate: number;
  apply_to_existing_vendors?: boolean;
}

export interface FeaturedRotationSettings {
  rotation_minutes: number;
  updated_at?: string | null;
}

export interface FeaturedRotationUpdate {
  rotation_minutes: number;
}

export interface DatabaseSyncResponse {
  status: 'success' | 'error';
  message: string;
  duration_seconds?: number;
}

/**
 * Get current exchange rate (public endpoint)
 */
export const getExchangeRate = async (): Promise<ExchangeRate> => {
  const response = await api.get<ExchangeRate>('/settings/public/exchange-rate');
  return response.data;
};

/**
 * Get all settings (admin only)
 */
export const getAllSettings = async (): Promise<Setting[]> => {
  const response = await api.get<Setting[]>('/settings/admin');
  return response.data;
};

/**
 * Update exchange rate (admin only)
 */
export const updateExchangeRate = async (rate: number): Promise<ExchangeRate> => {
  const response = await api.patch<ExchangeRate>(
    '/settings/admin/exchange-rate',
    { rate }
  );
  return response.data;
};

/**
 * Update a setting by key (admin only)
 */
export const updateSetting = async (key: string, value: string): Promise<Setting> => {
  const response = await api.patch<Setting>(
    `/settings/admin/${key}`,
    { value }
  );
  return response.data;
};

/**
 * Get shipping provider settings (public endpoint)
 */
export const getShippingProviderSettings = async (): Promise<ShippingProviderSettings> => {
  const response = await api.get<ShippingProviderSettings>('/settings/shipping-provider');
  return response.data;
};

/**
 * Update shipping provider settings (admin only)
 */
export const updateShippingProviderSettings = async (
  providerOrLegacy: 'manual' | 'shipbubble' | 'dhl' | boolean
): Promise<ShippingProviderSettings> => {
  const provider = typeof providerOrLegacy === 'boolean'
    ? (providerOrLegacy ? 'shipbubble' : 'manual')
    : providerOrLegacy;
  const response = await api.put<ShippingProviderSettings>(
    '/settings/shipping-provider',
    { provider }
  );
  return response.data;
};

/**
 * Get payout hold settings (admin only)
 */
export const getPayoutHoldSettings = async (): Promise<PayoutHoldSettings> => {
  const response = await api.get<PayoutHoldSettings>('/settings/admin/payout-hold');
  return response.data;
};

/**
 * Get featured rotation settings (public endpoint)
 */
export const getFeaturedRotationSettings = async (): Promise<FeaturedRotationSettings> => {
  const response = await api.get<FeaturedRotationSettings>('/settings/public/featured-rotation');
  return response.data;
};

/**
 * Get featured rotation settings (admin only)
 */
export const getAdminFeaturedRotationSettings = async (): Promise<FeaturedRotationSettings> => {
  const response = await api.get<FeaturedRotationSettings>('/settings/admin/featured-rotation');
  return response.data;
};

/**
 * Update featured rotation settings (admin only)
 */
export const updateFeaturedRotationSettings = async (
  rotationMinutes: number
): Promise<FeaturedRotationSettings> => {
  const response = await api.put<FeaturedRotationSettings>(
    '/settings/admin/featured-rotation',
    { rotation_minutes: rotationMinutes }
  );
  return response.data;
};

/**
 * Update payout hold settings (admin only)
 */
export const updatePayoutHoldSettings = async (
  holdDays: number
): Promise<PayoutHoldSettings> => {
  const response = await api.put<PayoutHoldSettings>(
    '/settings/admin/payout-hold',
    { hold_days: holdDays }
  );
  return response.data;
};

/**
 * Get commission settings (admin only)
 */
export const getCommissionSettings = async (): Promise<CommissionSettings> => {
  const response = await api.get<CommissionSettings>('/settings/admin/commission');
  return response.data;
};

/**
 * Update commission settings (admin only)
 */
export const updateCommissionSettings = async (
  commissionRate: number,
  applyToExistingVendors: boolean = false
): Promise<CommissionSettings> => {
  const response = await api.put<CommissionSettings>(
    '/settings/admin/commission',
    {
      commission_rate: commissionRate,
      apply_to_existing_vendors: applyToExistingVendors,
    }
  );
  return response.data;
};

/**
 * Sync Render database to local database (admin only, development only).
 */
export const syncRenderDatabase = async (): Promise<DatabaseSyncResponse> => {
  const response = await api.post<DatabaseSyncResponse>(
    '/settings/admin/db-sync',
    undefined,
    { timeout: 0 }
  );
  return response.data;
};

export interface ManualShippingRate {
  id: string;
  name: string;
  description: string | null;
  country: string;
  state: string | null;
  base_rate: number;
  min_order_value: number | null;
  max_order_value: number | null;
  min_delivery_days: number;
  max_delivery_days: number;
  is_active: boolean;
  is_default: boolean;
  priority: number;
}
export type ManualShippingRateInput = Omit<ManualShippingRate, 'id'>;
export const getManualShippingRates = async (): Promise<ManualShippingRate[]> =>
  (await api.get<{ shipping_rates: ManualShippingRate[] }>('/shipping-rates')).data.shipping_rates;
export const saveManualShippingRate = async (data: ManualShippingRateInput, id?: string): Promise<ManualShippingRate> =>
  (id ? await api.put<ManualShippingRate>(`/shipping-rates/${id}`, data) : await api.post<ManualShippingRate>('/shipping-rates', data)).data;
export const deactivateManualShippingRate = async (id: string): Promise<void> => {
  await api.delete(`/shipping-rates/${id}`);
};
export const setDefaultManualShippingRate = async (id: string): Promise<ManualShippingRate> =>
  (await api.post<ManualShippingRate>(`/shipping-rates/${id}/set-default`)).data;
export const previewManualShippingRates = async (data: { country: string; state: string; order_value: number }): Promise<{ available_rates: ManualShippingRate[] }> =>
  (await api.post('/shipping-rates/calculate', data)).data;
