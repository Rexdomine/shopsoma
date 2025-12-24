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
  use_shipbubble: boolean;
}

export interface ShippingProviderUpdate {
  use_shipbubble: boolean;
}

export interface PayoutHoldSettings {
  hold_days: number;
  updated_at?: string | null;
}

export interface PayoutHoldUpdate {
  hold_days: number;
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
  useShipBubble: boolean
): Promise<ShippingProviderSettings> => {
  const response = await api.put<ShippingProviderSettings>(
    '/settings/shipping-provider',
    { use_shipbubble: useShipBubble }
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
