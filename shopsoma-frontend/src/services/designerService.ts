import api from './api';

export interface Designer {
  id: string;
  business_name: string;
  logo_url: string | null;
  business_description?: string | null;
  featured_storefront_image_url?: string | null;
  is_featured_storefront?: boolean;
  total_products: number;
  total_orders: number;
  created_at: string;
}

export const designerService = {
  async listDesigners(): Promise<Designer[]> {
    const response = await api.get('/designers');
    return response.data;
  },
};
