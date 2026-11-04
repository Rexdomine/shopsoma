import api from './api';
import { normalizeProductImageUrl } from '../utils/productImages';

export interface DesignerCategory {
  id: string;
  name: string;
  slug: string;
  display_order: number;
  is_active: boolean;
}

export interface Designer {
  id: string;
  business_name: string;
  business_description?: string | null;
  logo_url: string | null;
  featured_storefront_image_url?: string | null;
  image_url?: string | null;
  campaign_image_url?: string | null;
  total_products: number;
  published_products_count?: number;
  total_orders: number;
  categories?: DesignerCategory[];
  created_at: string;
}

export const DEFAULT_DESIGNER_IMAGE_FALLBACK = '/images/hero/shop-edits-2088.jpg';

export const resolveDesignerAssetUrl = (rawUrl?: string | null): string => {
  const trimmed = rawUrl?.trim();
  if (!trimmed) return '';
  if (trimmed.startsWith('/images/')) {
    return trimmed;
  }
  return normalizeProductImageUrl(trimmed);
};

export const getDesignerDirectoryImageUrl = (designer: Designer): string => {
  const candidates = [
    designer.image_url,
    designer.campaign_image_url,
    designer.featured_storefront_image_url,
    designer.logo_url,
  ];
  for (const candidate of candidates) {
    const resolved = resolveDesignerAssetUrl(candidate);
    if (resolved) return resolved;
  }
  return DEFAULT_DESIGNER_IMAGE_FALLBACK;
};

export const getDesignerCampaignImageUrl = (
  designer: Designer,
  fallbackProductImageUrl?: string | null,
): string => {
  const candidates = [
    designer.campaign_image_url,
    designer.featured_storefront_image_url,
    designer.image_url,
    fallbackProductImageUrl,
    designer.logo_url,
  ];
  for (const candidate of candidates) {
    const resolved = resolveDesignerAssetUrl(candidate);
    if (resolved) return resolved;
  }
  return DEFAULT_DESIGNER_IMAGE_FALLBACK;
};

export const designerService = {
  async listDesigners(params?: { search?: string; letter?: string }): Promise<Designer[]> {
    const response = await api.get('/designers', { params });
    return response.data;
  },

  async getDesigner(designerId: string): Promise<Designer> {
    const response = await api.get(`/designers/${designerId}`);
    return response.data;
  },
};
