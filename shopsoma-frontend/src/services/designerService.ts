import api from './api';

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
  logo_url: string | null;
  business_description?: string | null;
  featured_storefront_image_url?: string | null;
  is_featured_storefront?: boolean;
  image_url?: string | null;
  campaign_image_url?: string | null;
  published_products_count?: number;
  categories?: DesignerCategory[];
  total_products: number;
  total_orders: number;
  created_at: string;
}

export const designerService = {
  async listDesigners(): Promise<Designer[]> {
    const response = await api.get('/designers');
    return response.data;
  },

  async getDesigner(designerId: string): Promise<Designer> {
    const response = await api.get(`/designers/${designerId}`);
    return response.data;
  },
};
