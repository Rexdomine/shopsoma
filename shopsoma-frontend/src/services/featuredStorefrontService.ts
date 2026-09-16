import api from './api';

export interface FeaturedStorefrontVendor {
  id: string;
  business_name: string;
  featured_storefront_image_url: string;
  product_count: number;
}

export const getFeaturedStorefrontVendors = async (
  category: 'men' | 'women',
): Promise<FeaturedStorefrontVendor[]> => (
  await api.get<FeaturedStorefrontVendor[]>('/designers/featured', { params: { category } })
).data;
