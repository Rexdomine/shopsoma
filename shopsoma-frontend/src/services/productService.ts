import api from './api';
import type { Product } from '../types';

export interface ProductListParams {
  page?: number;
  page_size?: number;
  category_id?: string;
  min_price?: number;
  max_price?: number;
  vendor_id?: string;
  is_featured?: boolean;
  search?: string;
  sort_by?: 'created_at' | 'title' | 'base_price' | 'orders_count' | 'views_count';
  sort_order?: 'asc' | 'desc';
  in_stock?: boolean;
  status?: string;
}

export interface ProductListResponse {
  products: Product[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export const productService = {
  // Get all products with filters
  async getProducts(params?: ProductListParams): Promise<ProductListResponse> {
    const response = await api.get('/products', { params });
    return response.data;
  },

  // Get single product by ID
  async getProduct(productId: string): Promise<Product> {
    const response = await api.get(`/products/${productId}`);
    return response.data;
  },

  // Get featured products
  async getFeaturedProducts(pageSize: number = 8): Promise<Product[]> {
    const response = await api.get('/products', {
      params: {
        is_featured: true,
        page_size: pageSize,
        sort_by: 'created_at',
        sort_order: 'desc'
      },
    });
    return response.data.products;
  },

  // Get products by category
  async getProductsByCategory(
    categoryId: string,
    pageSize?: number
  ): Promise<Product[]> {
    const response = await api.get('/products', {
      params: {
        category_id: categoryId,
        page_size: pageSize,
        sort_by: 'created_at',
        sort_order: 'desc'
      },
    });
    return response.data.products;
  },

  // Search products
  async searchProducts(
    query: string,
    params?: ProductListParams
  ): Promise<ProductListResponse> {
    const response = await api.get('/products', {
      params: { search: query, ...params },
    });
    return response.data;
  },

  // Get vendor products
  async getVendorProducts(
    vendorId: string,
    params?: ProductListParams
  ): Promise<ProductListResponse> {
    const response = await api.get('/products', {
      params: { vendor_id: vendorId, ...params },
    });
    return response.data;
  },

  // Create product (vendor only)
  async createProduct(productData: Partial<Product>): Promise<Product> {
    const response = await api.post('/products', productData);
    return response.data;
  },

  // Update product (vendor only)
  async updateProduct(
    productId: string,
    productData: Partial<Product>
  ): Promise<Product> {
    const response = await api.put(`/products/${productId}`, productData);
    return response.data;
  },

  // Delete product (vendor only)
  async deleteProduct(productId: string): Promise<void> {
    await api.delete(`/products/${productId}`);
  },
};
