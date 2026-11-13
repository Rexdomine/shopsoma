import api from './api';

export type DiscountType = 'percentage' | 'fixed_amount';

export interface PromoCode {
  id: string;
  code: string;
  description?: string | null;
  discount_type: DiscountType;
  discount_value: number;
  min_purchase_amount?: number | null;
  max_discount_amount?: number | null;
  usage_limit?: number | null;
  usage_limit_per_user: number;
  usage_count: number;
  valid_from: string;
  valid_until: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface PromoCodeListResponse {
  promo_codes: PromoCode[];
  total: number;
}

export interface PromoCodeCreatePayload {
  code: string;
  description?: string | null;
  discount_type: DiscountType;
  discount_value: number;
  min_purchase_amount?: number | null;
  max_discount_amount?: number | null;
  usage_limit?: number | null;
  usage_limit_per_user?: number;
  valid_from: string;
  valid_until: string;
  is_active: boolean;
}

export type PromoCodeUpdatePayload = Partial<PromoCodeCreatePayload>;

export const promoCodeService = {
  async listPromoCodes(params?: { active_only?: boolean; search?: string }): Promise<PromoCodeListResponse> {
    const response = await api.get('/promo-codes', { params });
    return response.data;
  },

  async getPromoCode(promoId: string): Promise<PromoCode> {
    const response = await api.get(`/promo-codes/${promoId}`);
    return response.data;
  },

  async createPromoCode(payload: PromoCodeCreatePayload): Promise<PromoCode> {
    const response = await api.post('/promo-codes', payload);
    return response.data;
  },

  async updatePromoCode(promoId: string, payload: PromoCodeUpdatePayload): Promise<PromoCode> {
    const response = await api.put(`/promo-codes/${promoId}`, payload);
    return response.data;
  },

  async deletePromoCode(promoId: string): Promise<void> {
    await api.delete(`/promo-codes/${promoId}`);
  },
};
