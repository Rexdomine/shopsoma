import api from './api';
import type { Product, ProductImage, ImageUploadResponse, ImageBatchUploadResponse } from '../types';

export interface CreateProductImagePayload {
  image_url: string;
  thumbnail_url?: string;
  alt_text?: string;
  display_order?: number;
  is_primary?: boolean;
  storage_keys?: string[];
}

export interface CreateProductVariantPayload {
  size?: string;
  color?: string;
  color_hex?: string;
  price: number;
  stock: number;
  sku?: string;
  is_available?: boolean;
}

export interface CreateProductVariationPayload {
  title: string;
  type?: string;
  color_hex?: string;
  price?: number;
  sale_price?: number;
  inherits_price?: boolean;
  inherits_sale_price?: boolean;
  images?: string[];
  is_active?: boolean;
  sizes: Array<{
    size: string;
    stock: number;
  }>;
}

export interface CreateProductPayload {
  title: string;
  description?: string;
  category_id?: string;
  collection_id?: string;
  sku?: string;
  base_price: number;
  compare_at_price?: number;
  currency?: 'NGN' | 'USD';
  total_stock?: number;
  status?: 'draft' | 'active' | 'inactive' | 'archived';
  is_featured?: boolean;
  product_type?: 'single' | 'variable';
  made_to_order?: boolean;
  made_to_order_timeline?: string;
  care_instructions?: string;
  fabric_composition?: string;
  weight_kg?: number;
  length_cm?: number;
  width_cm?: number;
  height_cm?: number;
  meta_title?: string;
  meta_description?: string;
  images?: CreateProductImagePayload[];
  variants?: CreateProductVariantPayload[];
  variations?: CreateProductVariationPayload[];
}

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

  // Get vendor product by ID (vendor only)
  async getVendorProduct(productId: string): Promise<Product> {
    const response = await api.get(`/vendor/products/${productId}`, { timeout: 20000 });
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
    void vendorId;
    const response = await api.get('/vendor/products', {
      params,
    });
    return response.data;
  },

  // Create product (vendor only)
  async createProduct(productData: CreateProductPayload | FormData): Promise<Product> {
    const config = productData instanceof FormData
      ? { timeout: 20000, headers: { 'Content-Type': 'multipart/form-data' } }
      : { timeout: 20000 };
    const response = await api.post('/products', productData, config);
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

  // Duplicate product (vendor only)
  async duplicateProduct(productId: string): Promise<Product> {
    // No automatic POST retry: a lost response can still represent a saved draft.
    const config = { timeout: 10000, _retry: true };
    const response = await api.post(`/products/${productId}/duplicate`, undefined, config);
    return response.data;
  },

  // Add image to product (vendor only)
  async addProductImage(
    productId: string,
    imageData: CreateProductImagePayload
  ): Promise<ProductImage> {
    const response = await api.post(`/products/${productId}/images`, imageData);
    return response.data;
  },

  // Delete product image (vendor only)
  async deleteProductImage(
    productId: string,
    imageId: string
  ): Promise<void> {
    await api.delete(`/products/${productId}/images/${imageId}`);
  },

  // Upload single image
  async uploadImage(
    file: File,
    folder: string = 'products',
    generateVariants: boolean = true
  ): Promise<ImageUploadResponse> {
    const formData = new FormData();
    formData.append('file', file);

    const response = await api.post('/images/upload', formData, {
      params: {
        folder,
        generate_variants: generateVariants,
      },
      headers: {
        'Content-Type': 'multipart/form-data',
      },
      timeout: 60000,
    });
    return response.data;
  },

  // Upload multiple images
  async uploadImages(
    files: File[],
    folder: string = 'products',
    generateVariants: boolean = true
  ): Promise<ImageBatchUploadResponse> {
    const formData = new FormData();
    files.forEach((file) => {
      formData.append('files', file);
    });

    const response = await api.post('/images/upload/batch', formData, {
      params: {
        folder,
        generate_variants: generateVariants,
      },
      headers: {
        'Content-Type': 'multipart/form-data',
      },
      timeout: 60000,
    });
    return response.data;
  },

  async bulkUploadSingleProducts(file: File): Promise<{ created_count: number }> {
    const formData = new FormData();
    formData.append('file', file);

    const response = await api.post('/products/bulk-upload/single', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
      timeout: 30000,
    });
    return response.data;
  },

  async bulkUploadVariableProducts(file: File): Promise<{ created_count: number }> {
    const formData = new FormData();
    formData.append('file', file);

    const response = await api.post('/products/bulk-upload/variable', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
      timeout: 30000,
    });
    return response.data;
  },
};
